import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from server import Store, parse_file, parse_codex, local_files, MAX_JSON


def fixture():
    return [{'id': 'synthetic-chat-1', 'title': '合成项目 100%_完成', 'current_node': 'a2', 'mapping': {
        'root': {'parent': None, 'message': None},
        'u': {'parent': 'root', 'message': {'author': {'role': 'user'}, 'content': {'parts': ['如何测试？']}}},
        'a1': {'parent': 'u', 'message': {'author': {'role': 'assistant'}, 'content': {'parts': ['分支一：火星']}}},
        'a2': {'parent': 'u', 'message': {'author': {'role': 'assistant'}, 'content': {'parts': ['分支二：合成示例']}}},
    }}]


def records(data=None, label='合成账号 A'):
    return parse_file(io.BytesIO(json.dumps(data if data is not None else fixture()).encode()), 'conversations.json', label)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='shiliao-test-')
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'history.sqlite')

    def test_dedup_update_and_account_isolation(self):
        self.assertEqual(self.store.import_records(records())['added'], 1)
        self.assertEqual(self.store.import_records(records())['unchanged'], 1)
        changed = fixture()
        changed[0]['mapping']['a2']['message']['content']['parts'] = ['新的回答']
        self.assertEqual(self.store.import_records(records(changed))['updated'], 1)
        self.assertEqual(self.store.import_records(records(label='合成账号 B'))['added'], 1)
        self.assertEqual(self.store.stats()['conversations'], 2)

    def test_search_non_current_branch_and_literal_like_symbols(self):
        self.store.import_records(records())
        self.assertEqual(self.store.list(q='火星')['total'], 1)
        self.assertEqual(self.store.list(q='100%_')['total'], 1)
        self.assertEqual(self.store.list(q="%' OR 1=1 --")['total'], 0)
        self.assertEqual(self.store.list(label='unknown')['total'], 0)

    def test_json_roundtrip_preserves_all_branches(self):
        self.store.import_records(records())
        exported = self.store.export_records({'format': 'json'})
        second = Store(Path(self.temp.name) / 'second.sqlite')
        second.import_records(parse_file(io.BytesIO(exported['content'].encode()), 'backup.json'))
        key = second.list()['items'][0]['key']
        self.assertEqual(second.get(key, 'a1')['messages'][-1]['text'], '分支一：火星')
        self.assertEqual(second.get(key, 'a2')['messages'][-1]['text'], '分支二：合成示例')

    def test_selected_branch_roundtrip(self):
        self.store.import_records(records())
        key = self.store.list()['items'][0]['key']
        result = self.store.export_records({'scope': 'conversation', 'format': 'json', 'key': key, 'branch': 'a1'})
        content = json.loads(result['content'])['conversations'][0]
        self.assertEqual(content['currentBranch'], 'a1')
        self.assertEqual(content['messages'][-1]['text'], '分支一：火星')
        with self.assertRaises(ValueError):
            self.store.get(key, 'unknown-branch')

    def test_markdown_text_and_filtered_exports(self):
        self.store.import_records(records())
        for format_name, marker in [('md', '## 用户'), ('txt', '【用户】')]:
            result = self.store.export_records({'scope': 'filtered', 'q': '火星', 'format': format_name})
            self.assertIn(marker, result['content'])
            self.assertIn('分支二：合成示例', result['content'])
            self.assertTrue(Path(result['path']).exists())
        with self.assertRaises(ValueError):
            self.store.export_records({'scope': 'filtered', 'q': 'not-in-synthetic-fixture'})

    def test_broken_input_rolls_back_entire_import(self):
        self.store.import_records(records())
        def failing():
            yield from records(label='synthetic-new-source')
            raise ValueError('synthetic failure')
        with self.assertRaises(ValueError):
            self.store.import_records(failing())
        self.assertEqual(self.store.stats()['conversations'], 1)
        with self.assertRaises(ValueError):
            list(parse_file(io.BytesIO(b'{invalid'), 'broken.json'))

    def test_zip_selects_only_history_and_does_not_extract(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('../../conversations.json', json.dumps(fixture()))
            archive.writestr('auth.json', 'not even valid JSON')
            archive.writestr('attachments/image.png', b'not an image')
        self.store.import_records(parse_file(stream, 'synthetic.zip'))
        self.assertEqual(self.store.stats()['conversations'], 1)
        self.assertFalse((Path(self.temp.name) / 'conversations.json').exists())

    def test_credentials_are_rejected_before_stream_is_read(self):
        class Unreadable:
            def seek(self, *args):
                raise AssertionError('Credential stream must not be touched')
        for name in ('auth.json', 'AUTH.JSON', 'nested/server-info.json'):
            with self.assertRaises(ValueError):
                list(parse_file(Unreadable(), name))

    def test_hidden_messages_and_analysis_are_skipped(self):
        data = [{'id': 'synthetic-visible', 'messages': [
            {'role': 'user', 'text': '合成问题'},
            {'role': 'assistant', 'text': 'hidden', 'metadata': {'is_visually_hidden_from_conversation': True}},
            {'role': 'assistant', 'text': 'internal', 'channel': 'analysis'},
            {'role': 'tool', 'text': 'tool output'},
            {'role': 'assistant', 'text': '合成公开回答'},
        ]}]
        self.assertEqual([m['text'] for m in list(records(data))[0]['messages']], ['合成问题', '合成公开回答'])

    def test_codex_events_avoid_injected_user_context_and_duplicate_answers(self):
        rows = [
            {'type': 'session_meta', 'payload': {'id': 'synthetic-codex'}},
            {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': '真实的合成用户输入'}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': 'injected environment'}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'channel': 'analysis', 'content': 'internal'}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'channel': 'final', 'content': [{'text': '合成回答'}]}},
            {'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': '合成回答'}},
        ]
        stream = io.BytesIO(('\n'.join(json.dumps(row) for row in rows) + '\n{truncated').encode())
        warnings = []
        record = list(parse_codex(stream, 'A', 'synthetic.jsonl', warnings))[0]
        self.assertEqual([m['text'] for m in record['messages']], ['真实的合成用户输入', '合成回答'])
        self.assertEqual(len(warnings), 1)

    def test_prompt_history_does_not_replace_full_session(self):
        self.store.import_records(records())
        reduced = list(records())[0]
        reduced['recordKind'] = 'prompt-history'
        reduced['messages'] = reduced['messages'][:1]
        self.assertEqual(self.store.import_records([reduced])['unchanged'], 1)
        self.assertEqual(self.store.stats()['messages'], 2)

    def test_size_limit_without_allocating_large_payload(self):
        class Large(io.BytesIO):
            def tell(self):
                return MAX_JSON + 1
        with self.assertRaises(ValueError):
            list(parse_file(Large(b'[]'), 'large.json'))

    def test_local_scan_excludes_auth_and_outside_symlinks(self):
        home = Path(self.temp.name) / 'codex-home'
        sessions = home / 'sessions'
        sessions.mkdir(parents=True)
        (home / 'auth.json').write_text('synthetic-not-a-token')
        (home / 'history.jsonl').write_text('{}')
        (sessions / 'session.jsonl').write_text('{}')
        outside = Path(self.temp.name) / 'outside.jsonl'
        outside.write_text('{}')
        try:
            (sessions / 'link.jsonl').symlink_to(outside)
        except OSError:
            pass  # Windows may require Developer Mode for symlinks.
        self.assertEqual({path.name for path in local_files(home)}, {'session.jsonl', 'history.jsonl'})


if __name__ == '__main__':
    unittest.main()
