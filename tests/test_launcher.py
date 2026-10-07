import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import app_launcher
import uninstall


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='shiliao-launch-test-')
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'LOCALAPPDATA': self.temp.name, 'CODEX_ACCESS_TOKEN': 'synthetic-placeholder',
                              'OPENAI_API_KEY': 'synthetic-placeholder', 'CODEX_HOME': 'synthetic-parent-home'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.detect = patch.object(app_launcher, 'installed_executable', return_value={'executable': 'C:/Synthetic/Codex.exe', 'version': 'synthetic'})
        self.detect.start()
        self.addCleanup(self.detect.stop)

    def test_dry_run_never_creates_profile_or_starts_process(self):
        with patch.object(app_launcher.subprocess, 'Popen') as process:
            result = app_launcher.launch_profiles(['A', 'B', 'B'], dry_run=True)
        process.assert_not_called()
        self.assertEqual([item['profile'] for item in result['launched']], ['A', 'B'])
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_profile_b_is_separate_and_inherited_credentials_are_removed(self):
        with patch.object(app_launcher.subprocess, 'Popen', return_value=Mock(pid=123)) as process:
            app_launcher.launch_profiles(['A', 'B'])
        account_a, account_b = process.call_args_list
        for call in (account_a, account_b):
            for name in app_launcher.EXCLUDED_ENV:
                if name not in ('CODEX_HOME', 'CODEX_ELECTRON_USER_DATA_PATH'):
                    self.assertNotIn(name, call.kwargs['env'])
        self.assertNotIn('CODEX_HOME', account_a.kwargs['env'])
        home_b = Path(account_b.kwargs['env']['CODEX_HOME'])
        self.assertTrue(home_b.is_relative_to(Path(self.temp.name)))
        self.assertFalse((home_b / 'auth.json').exists())
        self.assertEqual((home_b / 'config.toml').read_text(), 'cli_auth_credentials_store = "file"\n')
        self.assertTrue(any(argument.startswith('--user-data-dir=') for argument in account_b.args[0]))

    def test_existing_b_config_is_kept(self):
        home_b = Path(self.temp.name) / 'ChatGPT-DualAccount-Test/B/codex-home'
        home_b.mkdir(parents=True)
        config = home_b / 'config.toml'
        config.write_text('# synthetic custom setting\n')
        with patch.object(app_launcher.subprocess, 'Popen', return_value=Mock(pid=123)):
            app_launcher.launch_profiles(['B'])
        self.assertEqual(config.read_text(), '# synthetic custom setting\n')

    def test_invalid_profile_is_rejected(self):
        for profiles in ([], ['C'], 'B', None):
            with self.assertRaises(ValueError):
                app_launcher.launch_profiles(profiles)

    def test_uninstall_scan_has_no_developer_workspace_roots(self):
        with patch.dict(os.environ, {'USERPROFILE': self.temp.name}):
            self.assertEqual(uninstall.known_roots(), [Path(self.temp.name) / 'Desktop'])


if __name__ == '__main__':
    unittest.main()
