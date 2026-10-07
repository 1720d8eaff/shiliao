"""Local, read-only history importer. Python standard library only."""
from contextlib import contextmanager
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import zipfile

APP_ID = 'local-chat-history-importer-v1'
MAX_UPLOAD = 512 * 1024 * 1024
MAX_JSON = 128 * 1024 * 1024
MAX_LINE = 32 * 1024 * 1024


class ImportErrorWithMessage(ValueError):
    pass


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def stamp(value):
    try:
        if isinstance(value, (int, float)):
            return dt.datetime.fromtimestamp(value / 1000 if value > 100000000000 else value, dt.timezone.utc).isoformat()
        if isinstance(value, str) and value:
            parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
            return parsed.replace(tzinfo=parsed.tzinfo or dt.timezone.utc).astimezone(dt.timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    return ''


def content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(filter(None, (content_text(part) for part in content)))
    if not isinstance(content, dict):
        return ''
    if isinstance(content.get('text'), str):
        return content['text']
    if isinstance(content.get('parts'), list):
        return content_text(content['parts'])
    return ''


def visible_message(message, fallback_id='', timestamp=''):
    if not isinstance(message, dict):
        return None
    author = message.get('author') or {}
    role = message.get('role') or (author.get('role') if isinstance(author, dict) else None)
    if role not in ('user', 'assistant') or message.get('channel') == 'analysis':
        return None
    metadata = message.get('metadata') or {}
    if isinstance(metadata, dict) and metadata.get('is_visually_hidden_from_conversation'):
        return None
    text = content_text(message.get('content', message.get('text', ''))).strip()
    if not text:
        return None
    return {'id': str(message.get('id') or fallback_id), 'role': role, 'text': text,
            'timestamp': stamp(message.get('create_time', message.get('timestamp', timestamp)))}


def branch_messages(nodes, leaf):
    lookup = {node['id']: node for node in nodes}
    seen, selected = set(), []
    while leaf in lookup and leaf not in seen:
        seen.add(leaf)
        node = lookup[leaf]
        if node.get('message'):
            selected.append(node['message'])
        leaf = node.get('parent')
    return list(reversed(selected))


def make_conversation(kind, label, external_id, title, messages, created='', updated='', **extras):
    if not messages:
        return None
    external_id = str(external_id or hashlib.sha256(encode(messages).encode()).hexdigest())
    return {'source': kind, 'label': str(label or kind)[:100], 'externalId': external_id,
            'title': str(title or next((m['text'][:70] for m in messages if m['role'] == 'user'), '未命名对话'))[:300],
            'created': stamp(created) or messages[0].get('timestamp', ''),
            'updated': stamp(updated) or messages[-1].get('timestamp', ''),
            'messages': messages, **extras}


def parse_chatgpt(data, label):
    if isinstance(data, dict) and isinstance(data.get('conversations'), list):
        data = data['conversations']
    elif isinstance(data, dict) and ('mapping' in data or 'messages' in data):
        data = [data]
    if not isinstance(data, list):
        raise ImportErrorWithMessage('这不是 ChatGPT 对话导出文件。请选择 conversations.json 或导出 ZIP。')
    for entry in data:
        if not isinstance(entry, dict):
            continue
        mapping = entry.get('mapping')
        extras = {}
        if isinstance(mapping, dict):
            nodes = []
            for key, node in mapping.items():
                if not isinstance(node, dict):
                    continue
                nodes.append({'id': str(key), 'parent': str(node['parent']) if node.get('parent') is not None else None,
                              'message': visible_message(node.get('message'), str(key))})
            parents = {node['parent'] for node in nodes if node['parent']}
            leaves = [node['id'] for node in nodes if node['id'] not in parents]
            leaves = [leaf for leaf in leaves if branch_messages(nodes, leaf)]
            current = str(entry.get('current_node') or '')
            if not branch_messages(nodes, current):
                current = leaves[-1] if leaves else ''
            messages = branch_messages(nodes, current)
            extras = {'nodes': nodes, 'branches': leaves, 'currentBranch': current}
        elif isinstance(entry.get('messages'), list):
            messages = [m for i, raw in enumerate(entry['messages']) if (m := visible_message(raw, str(i)))]
        else:
            continue
        result = make_conversation('chatgpt', label, entry.get('id') or entry.get('conversation_id'), entry.get('title'),
                                   messages, entry.get('create_time'), entry.get('update_time'), **extras)
        if result:
            yield result


def parse_codex(stream, label, filename, warnings):
    responses, events, history = [], [], {}
    meta, truncated = {}, 0
    for ordinal, raw in enumerate(stream):
        if len(raw) > MAX_LINE:
            raise ImportErrorWithMessage('单行 JSONL 超过 32 MB，请先分割导出文件。')
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            truncated += 1
            continue
        if not isinstance(row, dict):
            continue
        payload = row.get('payload') or {}
        typ = row.get('type')
        if typ == 'session_meta' and isinstance(payload, dict):
            if not meta:
                meta = payload
        elif typ == 'response_item' and isinstance(payload, dict) and payload.get('type') == 'message':
            msg = visible_message(payload, str(ordinal), row.get('timestamp'))
            if msg:
                responses.append((ordinal, msg))
        elif typ == 'event_msg' and isinstance(payload, dict):
            event_kind = payload.get('type')
            role = 'user' if event_kind == 'user_message' else 'assistant' if event_kind == 'agent_message' else None
            if event_kind == 'item_completed' and isinstance(payload.get('item'), dict):
                item = payload['item']
                item_type = str(item.get('type', '')).replace('_', '').lower()
                if item_type in ('usermessage', 'agentmessage'):
                    role = 'user' if item_type == 'usermessage' else 'assistant'
                    payload = {**item, 'message': item.get('message', item.get('text', item.get('content', '')))}
            if role and payload.get('phase') != 'analysis':
                msg = visible_message({'role': role, 'text': content_text(payload.get('message', ''))}, str(ordinal), row.get('timestamp'))
                if msg:
                    events.append((ordinal, msg))
        elif 'session_id' in row and isinstance(row.get('text'), str):
            sid = str(row['session_id'])
            msg = visible_message({'role': 'user', 'text': row['text']}, str(ordinal), row.get('ts'))
            if msg:
                history.setdefault(sid, []).append(msg)
    if truncated:
        warnings.append(f'{Path(filename).name}：跳过 {truncated} 行未完成或无效的 JSON。')
    if history and not responses and not events:
        for sid, messages in history.items():
            yield make_conversation('codex', label, sid, None, messages, recordKind='prompt-history')
        return
    # User events represent actual user input; response user items may also include injected context.
    # Responses preserve visible assistant commentary/final messages. Select one source per role.
    chosen = []
    for role in ('user', 'assistant'):
        preferred = events if role == 'user' else responses
        fallback = responses if role == 'user' else events
        chosen.extend([x for x in preferred if x[1]['role'] == role] or [x for x in fallback if x[1]['role'] == role])
    chosen.sort(key=lambda pair: pair[0])
    messages = [pair[1] for pair in chosen]
    result = make_conversation('codex', label, meta.get('id') or meta.get('session_id') or Path(filename).stem,
                               meta.get('title'), messages, meta.get('timestamp'), recordKind='session')
    if result:
        yield result


def parse_unified(data):
    if not isinstance(data, dict) or data.get('schema') != APP_ID or not isinstance(data.get('conversations'), list):
        raise ImportErrorWithMessage('无法识别统一历史备份格式。')
    for entry in data['conversations']:
        if not isinstance(entry, dict):
            continue
        messages = [m for i, raw in enumerate(entry.get('messages', [])) if (m := visible_message(raw, str(i)))]
        if not messages:
            continue
        extras = {'recordKind': entry['recordKind']} if entry.get('recordKind') in ('session', 'prompt-history') else {}
        if isinstance(entry.get('nodes'), list):
            nodes = [{'id': str(n.get('id', i)), 'parent': str(n['parent']) if n.get('parent') is not None else None,
                      'message': visible_message(n.get('message'), str(i))}
                     for i, n in enumerate(entry['nodes']) if isinstance(n, dict)]
            extras.update(nodes=nodes, branches=[str(b) for b in entry.get('branches', [])], currentBranch=str(entry.get('currentBranch', '')))
        yield make_conversation(entry.get('source') if entry.get('source') in ('chatgpt', 'codex') else 'chatgpt',
                                entry.get('label'), entry.get('externalId'), entry.get('title'), messages,
                                entry.get('created'), entry.get('updated'), **extras)


def parse_file(stream, filename, label='', source='auto', warnings=None):
    if Path(filename.replace('\\', '/')).name.casefold() in ('auth.json', 'server-info.json'):
        raise ImportErrorWithMessage('这是登录或服务配置文件，不是聊天记录。')
    warnings = warnings if warnings is not None else []
    stream.seek(0)
    prefix = stream.read(4)
    stream.seek(0)
    if prefix == b'PK\x03\x04' or filename.lower().endswith('.zip'):
        total, matched = 0, 0
        try:
            with zipfile.ZipFile(stream) as archive:
                for info in archive.infolist():
                    basename = Path(info.filename.replace('\\', '/')).name.lower()
                    selected = re.fullmatch(r'conversations(?:[._-]?\d+)?\.json', basename) or basename.endswith('.jsonl') or basename == 'chat-history-backup.json'
                    if info.is_dir() or not selected:
                        continue
                    total += info.file_size
                    if total > MAX_UPLOAD or info.file_size > MAX_UPLOAD:
                        raise ImportErrorWithMessage('ZIP 内所选记录超过 512 MB，请分批导入。')
                    matched += 1
                    with archive.open(info) as member:
                        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as scratch:
                            for block in iter(lambda: member.read(1024 * 1024), b''):
                                scratch.write(block)
                            yield from parse_file(scratch, basename, label, source, warnings)
                if not matched:
                    raise ImportErrorWithMessage('ZIP 中没有找到 conversations JSON 或 Codex JSONL 记录。')
        except (zipfile.BadZipFile, RuntimeError) as exc:
            raise ImportErrorWithMessage('ZIP 损坏或被加密，请解压后选择记录文件。') from exc
        return
    if filename.lower().endswith('.jsonl') or source == 'codex':
        yield from parse_codex(stream, label or 'Codex 导入', filename, warnings)
        return
    stream.seek(0, 2)
    if stream.tell() > MAX_JSON:
        raise ImportErrorWithMessage('单个 JSON 超过 128 MB，请拆分或分别导入编号文件。')
    stream.seek(0)
    try:
        data = json.loads(stream.read().decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportErrorWithMessage('JSON 格式无效。请选择导出的记录文件。') from exc
    if isinstance(data, dict) and data.get('schema') == APP_ID:
        yield from parse_unified(data)
    else:
        yield from parse_chatgpt(data, label or 'ChatGPT 导出')


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS conversations (
                key TEXT PRIMARY KEY, source TEXT, label TEXT, external_id TEXT, title TEXT,
                created TEXT, updated TEXT, message_count INTEGER, body TEXT, payload TEXT, digest TEXT)''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=60)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def import_records(self, records):
        counts = {'added': 0, 'updated': 0, 'unchanged': 0}
        with self.connect() as db:
            for record in records:
                if not record:
                    continue
                key = hashlib.sha256(encode([record['source'], record['label'], record['externalId']]).encode()).hexdigest()[:32]
                payload = encode(record)
                digest = hashlib.sha256(payload.encode()).hexdigest()
                old = db.execute('SELECT digest, payload FROM conversations WHERE key=?', (key,)).fetchone()
                if old and record.get('recordKind') == 'prompt-history' and json.loads(old['payload']).get('recordKind') != 'prompt-history':
                    counts['unchanged'] += 1
                    continue
                if old and old['digest'] == digest:
                    counts['unchanged'] += 1
                    continue
                counts['updated' if old else 'added'] += 1
                # Search every visible branch, even when the default view selects another branch.
                body = '\n'.join(m['text'] for m in record['messages'])
                body += '\n' + '\n'.join(n['message']['text'] for n in record.get('nodes', []) if n.get('message'))
                db.execute('INSERT OR REPLACE INTO conversations VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           (key, record['source'], record['label'], record['externalId'], record['title'],
                            record['created'], record['updated'], len(record['messages']), body, payload, digest))
        return counts

    def list(self, q='', source='', label='', offset=0, limit=80):
        conditions, args = [], []
        if q:
            conditions.append("(title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\')")
            term = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            args.extend([term, term])
        for column, value in (('source', source), ('label', label)):
            if value:
                conditions.append(column + '=?')
                args.append(value)
        where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
        with self.connect() as db:
            count = db.execute('SELECT COUNT(*) FROM conversations' + where, args).fetchone()[0]
            rows = db.execute('SELECT key, source, label, title, created, updated, message_count FROM conversations' + where + ' ORDER BY updated DESC, key LIMIT ? OFFSET ?', [*args, limit, offset]).fetchall()
        return {'total': count, 'items': [dict(row) for row in rows]}

    def get(self, key, branch=''):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM conversations WHERE key=?', (key,)).fetchone()
        if not row:
            return None
        record = json.loads(row['payload'])
        record['key'] = key
        if branch and record.get('nodes'):
            if branch not in record.get('branches', []) and branch != record.get('currentBranch'):
                raise ImportErrorWithMessage('没有找到所选对话分支。')
            record['messages'] = branch_messages(record['nodes'], branch)
        return record

    def stats(self):
        with self.connect() as db:
            total = db.execute('SELECT COUNT(*), COALESCE(SUM(message_count),0) FROM conversations').fetchone()
            labels = db.execute('SELECT label, source, COUNT(*) AS count FROM conversations GROUP BY label, source ORDER BY label').fetchall()
        return {'conversations': total[0], 'messages': total[1], 'labels': [dict(row) for row in labels]}

    def backup(self):
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM conversations ORDER BY updated DESC').fetchall()
        return {'schema': APP_ID, 'exportedAt': dt.datetime.now(dt.timezone.utc).isoformat(), 'conversations': [json.loads(r['payload']) for r in rows]}

    def save_backup(self):
        folder = self.path.parent / 'backups'
        folder.mkdir(parents=True, exist_ok=True)
        name = 'chat-history-backup-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3) + '.json'
        target = folder / name
        content = self.backup()
        temporary = target.with_suffix('.tmp')
        temporary.write_text(encode(content), encoding='utf-8')
        temporary.replace(target)
        return {'path': str(target.resolve()), 'filename': name, 'conversations': len(content['conversations']), 'backup': content}

    def export_records(self, options):
        if not isinstance(options, dict):
            raise ImportErrorWithMessage('请选择导出范围和格式。')
        scope, format_name = options.get('scope', 'all'), options.get('format', 'json')
        if scope not in ('all', 'filtered', 'conversation') or format_name not in ('json', 'md', 'txt'):
            raise ImportErrorWithMessage('请选择支持的导出范围和格式。')
        if scope == 'conversation':
            key, branch = str(options.get('key', '')), str(options.get('branch', ''))
            if not re.fullmatch('[a-f0-9]{32}', key):
                raise ImportErrorWithMessage('请先打开要导出的对话。')
            record = self.get(key, branch)
            if not record:
                raise ImportErrorWithMessage('没有找到要导出的对话。')
            record.pop('key', None)
            if branch and record.get('nodes'):
                record['currentBranch'] = branch
            records = [record]
        else:
            conditions, values = [], []
            if scope == 'filtered':
                query = str(options.get('q', '')).strip()
                if query:
                    conditions.append("(title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\')")
                    term = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
                    values.extend([term, term])
                for column in ('source', 'label'):
                    value = options.get(column, '')
                    if value:
                        conditions.append(column + '=?')
                        values.append(str(value))
            where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
            with self.connect() as db:
                rows = db.execute('SELECT payload FROM conversations' + where + ' ORDER BY updated DESC, key', values).fetchall()
            records = [json.loads(row['payload']) for row in rows]
        if not records:
            raise ImportErrorWithMessage('所选范围没有聊天记录，请先导入或调整筛选。')
        if format_name == 'json':
            content = encode({'schema': APP_ID, 'exportedAt': dt.datetime.now(dt.timezone.utc).isoformat(), 'conversations': records})
            mime = 'application/json;charset=utf-8'
        else:
            sections = []
            for record in records:
                if format_name == 'md':
                    section = '# ' + record['title'] + '\n\n来源：' + record['source'] + ' / ' + record['label'] + '\n\n'
                    section += '\n\n---\n\n'.join('## ' + ('用户' if m['role'] == 'user' else '助手') + '\n\n' + m['text'] for m in record['messages'])
                else:
                    section = record['title'] + '\n来源：' + record['source'] + ' / ' + record['label'] + '\n\n'
                    section += '\n\n'.join('【' + ('用户' if m['role'] == 'user' else '助手') + '】\n' + m['text'] for m in record['messages'])
                sections.append(section)
            content = ('\n\n' + '=' * 48 + '\n\n').join(sections) + '\n'
            mime = ('text/markdown' if format_name == 'md' else 'text/plain') + ';charset=utf-8'
        folder = self.path.parent / 'exports'
        folder.mkdir(parents=True, exist_ok=True)
        prefix = {'all': '全部记录', 'filtered': '筛选记录', 'conversation': '单段对话'}[scope]
        name = '拾聊-' + prefix + '-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3) + '.' + format_name
        target = folder / name
        temporary = target.with_suffix('.tmp')
        temporary.write_text(content, encoding='utf-8-sig' if format_name == 'txt' else 'utf-8')
        temporary.replace(target)
        return {'path': str(target.resolve()), 'filename': name, 'conversations': len(records),
                'messages': sum(len(record['messages']) for record in records), 'format': format_name, 'mime': mime, 'content': content}


def local_profiles():
    primary = Path(os.environ.get('USERPROFILE', str(Path.home()))) / '.codex'
    secondary = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share'))) / 'ChatGPT-DualAccount-Test' / 'B' / 'codex-home'
    result = []
    for ident, label, home in [('A', 'Codex · 账号 A', primary), ('B', 'Codex · 账号 B', secondary)]:
        result.append({'id': ident, 'label': label, 'path': str(home), 'exists': home.is_dir(),
                       'sessionCount': sum(1 for _ in local_files(home)) if home.is_dir() else 0})
    return result


def local_files(home, include_archived=True):
    home = Path(home).resolve()
    for sub in (('sessions', 'archived_sessions') if include_archived else ('sessions',)):
        directory = home / sub
        if directory.is_dir():
            for path in directory.rglob('*.jsonl'):
                # A symlink inside a history directory must not lead to another user's files.
                if path.is_file() and path.resolve().is_relative_to(home):
                    yield path
    history = home / 'history.jsonl'
    if history.is_file() and history.resolve().is_relative_to(home):
        yield history
