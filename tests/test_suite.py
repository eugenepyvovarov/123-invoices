import importlib.util
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
site_packages = next((ROOT / '.venv' / 'lib').glob('python*/site-packages'), None)
if site_packages is not None:
    sys.path.insert(0, str(site_packages))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')

class ChunkValidationTests(unittest.TestCase):
    def test_deploy_script_exports_canonical_compose_project_name(self):
        deploy_script = (ROOT / 'scripts' / 'deploy.sh').read_text()

        self.assertIn(
            'export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-03-invoices}"',
            deploy_script,
        )
        self.assertIn(
            'export INVOICES_IMAGE="${INVOICES_IMAGE:-${IMAGE}:${ROLLOUT_IMAGE_TAG}}"',
            deploy_script,
        )
        self.assertIn('export PHASE_APP="${PHASE_APP:-lifeisgoodlabs-invoices}"', deploy_script)
        self.assertIn('export PHASE_ENV="${PHASE_ENV:-Development}"', deploy_script)
        self.assertIn('"${PHASE_BIN}" secrets export "${missing_keys[@]}" --app "${PHASE_APP}" --env "${PHASE_ENV}" --format dotenv', deploy_script)
        self.assertIn('sync_managed_runtime_env', deploy_script)
        self.assertNotIn('sync_runtime_secret_key', deploy_script)
        self.assertIn('"${DOCKER_BIN}" compose pull web scheduler', deploy_script)
        self.assertRegex(
            deploy_script,
            r'"\$\{DOCKER_BIN\}" compose up -d web\n(?:.*\n)*"\$\{DOCKER_BIN\}" compose up -d scheduler',
        )
        self.assertIn('"${REPO_ROOT}/scripts/verify_deploy.sh"', deploy_script)

    def test_deploy_script_rolls_out_both_services_from_shared_image_reference(self):
        deploy_script = (ROOT / 'scripts' / 'deploy.sh').read_text()

        self.assertIn(
            'export ROLLOUT_IMAGE_TAG="${ROLLOUT_IMAGE_TAG:-${SHA_TAG}}"',
            deploy_script,
        )
        self.assertRegex(
            deploy_script,
            r'export INVOICES_IMAGE="\$\{INVOICES_IMAGE:-\$\{IMAGE\}:\$\{ROLLOUT_IMAGE_TAG\}\}"',
        )

    def test_deploy_script_defaults_project_name_and_rolls_out_both_services(self):
        deploy_script = (ROOT / 'scripts' / 'deploy.sh').read_text()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            scripts_dir = temp_path / 'scripts'
            scripts_dir.mkdir()

            deploy_copy = scripts_dir / 'deploy.sh'
            deploy_copy.write_text(deploy_script)
            deploy_copy.chmod(deploy_copy.stat().st_mode | stat.S_IEXEC)

            command_log = temp_path / 'command.log'
            docker_log = temp_path / 'docker.log'
            fake_docker = temp_path / 'docker'
            fake_docker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf 'project=%s command=%s\\n' \"${COMPOSE_PROJECT_NAME:-}\" \"$*\" >> \"${DOCKER_LOG}\"\n"
            )
            fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IEXEC)

            for script_name in ('build_and_push.sh', 'verify_deploy.sh'):
                script_path = scripts_dir / script_name
                script_path.write_text(
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    "printf '%s project=%s image=%s\\n' \"$(basename \"$0\")\" \"${COMPOSE_PROJECT_NAME:-}\" \"${INVOICES_IMAGE:-}\" >> \"${COMMAND_LOG}\"\n"
                )
                script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            for key in ('SECRET_KEY', 'RENDER_EXTERNAL_HOSTNAME', 'REGISTRY_USER', 'REGISTRY_PASSWORD'):
                env.pop(key, None)
            env.update(
                {
                    'DEPLOY_ENV_FILE': str(temp_path / '.missing-deploy.env'),
                    'PHASE_BIN': 'true',
                    'DOCKER_LOG': str(docker_log),
                    'COMMAND_LOG': str(command_log),
                    'PATH': f"{temp_path}:{env['PATH']}",
                    'SECRET_KEY': 'test-secret',
                    'RENDER_EXTERNAL_HOSTNAME': 'invoices.ultramac.work',
                    'IMAGE': 'registry.example.com/lifeisgoodlabs/invoices',
                    'SHA_TAG': 'abc1234',
                }
            )

            result = subprocess.run(
                [str(deploy_copy)],
                cwd=temp_path,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                command_log.read_text().splitlines(),
                [
                    'build_and_push.sh project=03-invoices image=registry.example.com/lifeisgoodlabs/invoices:abc1234',
                    'verify_deploy.sh project=03-invoices image=registry.example.com/lifeisgoodlabs/invoices:abc1234',
                ],
            )
            self.assertEqual(
                docker_log.read_text().splitlines(),
                [
                    'project=03-invoices command=compose pull web scheduler',
                    'project=03-invoices command=compose up -d web',
                    'project=03-invoices command=compose up -d scheduler',
                ],
            )

    def test_deploy_script_loads_missing_secrets_from_phase_and_syncs_runtime_env(self):
        deploy_script = (ROOT / 'scripts' / 'deploy.sh').read_text()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            scripts_dir = temp_path / 'scripts'
            scripts_dir.mkdir()

            deploy_copy = scripts_dir / 'deploy.sh'
            deploy_copy.write_text(deploy_script)
            deploy_copy.chmod(deploy_copy.stat().st_mode | stat.S_IEXEC)

            runtime_env_file = temp_path / '.env'
            runtime_env_file.write_text('DEBUG=0\n', encoding='utf-8')

            command_log = temp_path / 'command.log'
            docker_log = temp_path / 'docker.log'
            phase_log = temp_path / 'phase.log'

            fake_docker = temp_path / 'docker'
            fake_docker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf 'project=%s command=%s\\n' \"${COMPOSE_PROJECT_NAME:-}\" \"$*\" >> \"${DOCKER_LOG}\"\n"
            )
            fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IEXEC)

            fake_phase = temp_path / 'phase'
            fake_phase.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf '%s\\n' \"$*\" >> \"${PHASE_LOG}\"\n"
                "if [ \"$1\" = secrets ] && [ \"$2\" = export ]; then\n"
                "  cat <<'EOF'\n"
                "SECRET_KEY=phase-secret\n"
                "RENDER_EXTERNAL_HOSTNAME=invoices.ultramac.work\n"
                "REGISTRY_USER=phase-user\n"
                "REGISTRY_PASSWORD=phase-password\n"
                "EOF\n"
                "  exit 0\n"
                "fi\n"
                "exit 1\n"
            )
            fake_phase.chmod(fake_phase.stat().st_mode | stat.S_IEXEC)

            for script_name in ('build_and_push.sh', 'verify_deploy.sh'):
                script_path = scripts_dir / script_name
                script_path.write_text(
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    "printf '%s project=%s image=%s registry_user=%s registry_password=%s secret_key=%s render_host=%s allowed_hosts=%s csrf_origins=%s\\n' "
                    "\"$(basename \"$0\")\" "
                    "\"${COMPOSE_PROJECT_NAME:-}\" "
                    "\"${INVOICES_IMAGE:-}\" "
                    "\"${REGISTRY_USER:-}\" "
                    "\"${REGISTRY_PASSWORD:-}\" "
                    "\"${SECRET_KEY:-}\" "
                    "\"${RENDER_EXTERNAL_HOSTNAME:-}\" "
                    "\"${ALLOWED_HOSTS:-}\" "
                    "\"${CSRF_TRUSTED_ORIGINS:-}\" >> \"${COMMAND_LOG}\"\n"
                )
                script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            for key in ('SECRET_KEY', 'RENDER_EXTERNAL_HOSTNAME', 'REGISTRY_USER', 'REGISTRY_PASSWORD'):
                env.pop(key, None)
            env.update(
                {
                    'DEPLOY_ENV_FILE': str(temp_path / '.missing-deploy.env'),
                    'RUNTIME_ENV_FILE': str(runtime_env_file),
                    'DOCKER_LOG': str(docker_log),
                    'COMMAND_LOG': str(command_log),
                    'PHASE_LOG': str(phase_log),
                    'PATH': f"{temp_path}:{env['PATH']}",
                    'IMAGE': 'registry.example.com/lifeisgoodlabs/invoices',
                    'SHA_TAG': 'abc1234',
                }
            )

            result = subprocess.run(
                [str(deploy_copy)],
                cwd=temp_path,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                phase_log.read_text().splitlines(),
                [
                    'secrets export SECRET_KEY RENDER_EXTERNAL_HOSTNAME REGISTRY_USER REGISTRY_PASSWORD --app lifeisgoodlabs-invoices --env Development --format dotenv',
                ],
            )
            self.assertEqual(
                command_log.read_text().splitlines(),
                [
                    'build_and_push.sh project=03-invoices image=registry.example.com/lifeisgoodlabs/invoices:abc1234 registry_user=phase-user registry_password=phase-password secret_key=phase-secret render_host=invoices.ultramac.work allowed_hosts=127.0.0.1,localhost,invoices.ultramac.work csrf_origins=https://invoices.ultramac.work',
                    'verify_deploy.sh project=03-invoices image=registry.example.com/lifeisgoodlabs/invoices:abc1234 registry_user=phase-user registry_password=phase-password secret_key=phase-secret render_host=invoices.ultramac.work allowed_hosts=127.0.0.1,localhost,invoices.ultramac.work csrf_origins=https://invoices.ultramac.work',
                ],
            )
            self.assertEqual(
                docker_log.read_text().splitlines(),
                [
                    'project=03-invoices command=login git.ultramac.work -u phase-user --password-stdin',
                    'project=03-invoices command=compose pull web scheduler',
                    'project=03-invoices command=compose up -d web',
                    'project=03-invoices command=compose up -d scheduler',
                ],
            )
            self.assertEqual(
                runtime_env_file.read_text(encoding='utf-8').splitlines(),
                [
                    'DEBUG=0',
                    'SECRET_KEY=phase-secret',
                    'RENDER_EXTERNAL_HOSTNAME=invoices.ultramac.work',
                    'ALLOWED_HOSTS=127.0.0.1,localhost,invoices.ultramac.work',
                    'CSRF_TRUSTED_ORIGINS=https://invoices.ultramac.work',
                ],
            )

    def test_deploy_script_normalizes_managed_host_contract_with_explicit_extras(self):
        deploy_script = (ROOT / 'scripts' / 'deploy.sh').read_text()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            scripts_dir = temp_path / 'scripts'
            scripts_dir.mkdir()

            deploy_copy = scripts_dir / 'deploy.sh'
            deploy_copy.write_text(deploy_script)
            deploy_copy.chmod(deploy_copy.stat().st_mode | stat.S_IEXEC)

            command_log = temp_path / 'command.log'
            docker_log = temp_path / 'docker.log'
            fake_docker = temp_path / 'docker'
            fake_docker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf 'project=%s command=%s\\n' \"${COMPOSE_PROJECT_NAME:-}\" \"$*\" >> \"${DOCKER_LOG}\"\n"
            )
            fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IEXEC)

            for script_name in ('build_and_push.sh', 'verify_deploy.sh'):
                script_path = scripts_dir / script_name
                script_path.write_text(
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    "printf '%s host=%s allowed=%s csrf=%s\\n' "
                    "\"$(basename \"$0\")\" "
                    "\"${RENDER_EXTERNAL_HOSTNAME:-}\" "
                    "\"${ALLOWED_HOSTS:-}\" "
                    "\"${CSRF_TRUSTED_ORIGINS:-}\" >> \"${COMMAND_LOG}\"\n"
                )
                script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            for key in ('REGISTRY_USER', 'REGISTRY_PASSWORD'):
                env.pop(key, None)
            env.update(
                {
                    'DEPLOY_ENV_FILE': str(temp_path / '.missing-deploy.env'),
                    'PHASE_BIN': 'true',
                    'DOCKER_LOG': str(docker_log),
                    'COMMAND_LOG': str(command_log),
                    'PATH': f"{temp_path}:{env['PATH']}",
                    'SECRET_KEY': 'test-secret',
                    'RENDER_EXTERNAL_HOSTNAME': 'invoices.ultramac.work',
                    'ALLOWED_HOSTS': 'localhost, extra.example.com, invoices.ultramac.work',
                    'CSRF_TRUSTED_ORIGINS': 'https://extra.example.com, https://invoices.ultramac.work',
                    'IMAGE': 'registry.example.com/lifeisgoodlabs/invoices',
                    'SHA_TAG': 'abc1234',
                }
            )

            result = subprocess.run(
                [str(deploy_copy)],
                cwd=temp_path,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                command_log.read_text().splitlines(),
                [
                    'build_and_push.sh host=invoices.ultramac.work allowed=localhost,extra.example.com,invoices.ultramac.work,127.0.0.1 csrf=https://extra.example.com,https://invoices.ultramac.work',
                    'verify_deploy.sh host=invoices.ultramac.work allowed=localhost,extra.example.com,invoices.ultramac.work,127.0.0.1 csrf=https://extra.example.com,https://invoices.ultramac.work',
                ],
            )

    def test_deploy_script_upserts_managed_runtime_env_and_preserves_unrelated_entries(self):
        deploy_script = (ROOT / 'scripts' / 'deploy.sh').read_text()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            scripts_dir = temp_path / 'scripts'
            scripts_dir.mkdir()

            deploy_copy = scripts_dir / 'deploy.sh'
            deploy_copy.write_text(deploy_script)
            deploy_copy.chmod(deploy_copy.stat().st_mode | stat.S_IEXEC)

            runtime_env_file = temp_path / 'runtime.env'
            runtime_env_file.write_text(
                '\n'.join(
                    [
                        'DEBUG=0',
                        'SECRET_KEY=old-secret',
                        'ALLOWED_HOSTS=old.example.com',
                        'MAIL_FROM=ops@example.com',
                        'RENDER_EXTERNAL_HOSTNAME=old.example.com',
                        'CSRF_TRUSTED_ORIGINS=https://old.example.com',
                    ]
                )
                + '\n',
                encoding='utf-8',
            )

            command_log = temp_path / 'command.log'
            docker_log = temp_path / 'docker.log'
            fake_docker = temp_path / 'docker'
            fake_docker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf 'project=%s command=%s\\n' \"${COMPOSE_PROJECT_NAME:-}\" \"$*\" >> \"${DOCKER_LOG}\"\n"
            )
            fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IEXEC)

            for script_name in ('build_and_push.sh', 'verify_deploy.sh'):
                script_path = scripts_dir / script_name
                script_path.write_text(
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    "printf '%s\\n' \"$(basename \"$0\")\" >> \"${COMMAND_LOG}\"\n"
                )
                script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            for key in ('REGISTRY_USER', 'REGISTRY_PASSWORD'):
                env.pop(key, None)
            env.update(
                {
                    'DEPLOY_ENV_FILE': str(temp_path / '.missing-deploy.env'),
                    'RUNTIME_ENV_FILE': str(runtime_env_file),
                    'PHASE_BIN': 'true',
                    'DOCKER_LOG': str(docker_log),
                    'COMMAND_LOG': str(command_log),
                    'PATH': f"{temp_path}:{env['PATH']}",
                    'SECRET_KEY': 'new-secret',
                    'RENDER_EXTERNAL_HOSTNAME': 'invoices.ultramac.work',
                    'ALLOWED_HOSTS': 'localhost, extra.example.com, invoices.ultramac.work',
                    'CSRF_TRUSTED_ORIGINS': 'https://extra.example.com, https://invoices.ultramac.work',
                    'IMAGE': 'registry.example.com/lifeisgoodlabs/invoices',
                    'SHA_TAG': 'abc1234',
                }
            )

            result = subprocess.run(
                [str(deploy_copy)],
                cwd=temp_path,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                runtime_env_file.read_text(encoding='utf-8').splitlines(),
                [
                    'DEBUG=0',
                    'MAIL_FROM=ops@example.com',
                    'SECRET_KEY=new-secret',
                    'RENDER_EXTERNAL_HOSTNAME=invoices.ultramac.work',
                    'ALLOWED_HOSTS=localhost,extra.example.com,invoices.ultramac.work,127.0.0.1',
                    'CSRF_TRUSTED_ORIGINS=https://extra.example.com,https://invoices.ultramac.work',
                ],
            )
            self.assertFalse(list(temp_path.glob('.env.tmp.*')))

    def test_deploy_script_fails_before_rollout_when_managed_inputs_are_missing(self):
        deploy_script = (ROOT / 'scripts' / 'deploy.sh').read_text()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            scripts_dir = temp_path / 'scripts'
            scripts_dir.mkdir()

            deploy_copy = scripts_dir / 'deploy.sh'
            deploy_copy.write_text(deploy_script)
            deploy_copy.chmod(deploy_copy.stat().st_mode | stat.S_IEXEC)

            command_log = temp_path / 'command.log'
            fake_docker = temp_path / 'docker'
            fake_docker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf '%s\\n' \"$*\" >> \"${COMMAND_LOG}\"\n"
            )
            fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IEXEC)

            for script_name in ('build_and_push.sh', 'verify_deploy.sh'):
                script_path = scripts_dir / script_name
                script_path.write_text(
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    "printf '%s\\n' \"$(basename \"$0\")\" >> \"${COMMAND_LOG}\"\n"
                )
                script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            for key in ('SECRET_KEY', 'RENDER_EXTERNAL_HOSTNAME', 'REGISTRY_USER', 'REGISTRY_PASSWORD'):
                env.pop(key, None)
            env.update(
                {
                    'DEPLOY_ENV_FILE': str(temp_path / '.missing-deploy.env'),
                    'PHASE_BIN': 'true',
                    'COMMAND_LOG': str(command_log),
                    'PATH': f"{temp_path}:{env['PATH']}",
                }
            )

            result = subprocess.run(
                [str(deploy_copy)],
                cwd=temp_path,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Missing required deploy-managed runtime env: SECRET_KEY RENDER_EXTERNAL_HOSTNAME.', result.stderr)
            self.assertFalse(command_log.exists())

    def test_canonical_deploy_command_runs_full_rollout_and_verification_flow(self):
        deploy_script = (ROOT / 'scripts' / 'deploy.sh').read_text()
        verify_script = (ROOT / 'scripts' / 'verify_deploy.sh').read_text()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            scripts_dir = temp_path / 'scripts'
            scripts_dir.mkdir()

            deploy_copy = scripts_dir / 'deploy.sh'
            deploy_copy.write_text(deploy_script)
            deploy_copy.chmod(deploy_copy.stat().st_mode | stat.S_IEXEC)

            verify_copy = scripts_dir / 'verify_deploy.sh'
            verify_copy.write_text(verify_script)
            verify_copy.chmod(verify_copy.stat().st_mode | stat.S_IEXEC)

            command_log = temp_path / 'command.log'
            docker_log = temp_path / 'docker.log'
            python_log = temp_path / 'python.log'
            python_attempts = temp_path / 'python-attempts.txt'

            fake_build = scripts_dir / 'build_and_push.sh'
            fake_build.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf 'build project=%s image=%s\\n' \"${COMPOSE_PROJECT_NAME:-}\" \"${INVOICES_IMAGE:-}\" >> \"${COMMAND_LOG}\"\n"
            )
            fake_build.chmod(fake_build.stat().st_mode | stat.S_IEXEC)

            fake_docker = temp_path / 'docker'
            fake_docker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf 'project=%s command=%s\\n' \"${COMPOSE_PROJECT_NAME:-}\" \"$*\" >> \"${DOCKER_LOG}\"\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = ps ] && [ \"$3\" = --services ] && [ \"$4\" = --status ] && [ \"$5\" = running ]; then\n"
                "  printf '%s\\n' \"$6\"\n"
                "  exit 0\n"
                "fi\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = logs ] && [ \"$3\" = --no-color ] && [ \"$4\" = --tail ]; then\n"
                "  printf 'Scheduler tick completed without startup errors\\n'\n"
                "  exit 0\n"
                "fi\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = ps ] && [ \"$3\" = -q ]; then\n"
                "  printf 'container-%s\\n' \"$4\"\n"
                "  exit 0\n"
                "fi\n"
                "if [ \"$1\" = inspect ] && [ \"$2\" = -f ]; then\n"
                "  case \"$3\" in\n"
                "    *com.docker.compose.project*) printf '%s\\n' \"${COMPOSE_PROJECT_NAME}\" ;;\n"
                "    *'.Name'*) printf '/%s\\n' \"${COMPOSE_PROJECT_NAME}-${4#container-}-1\" ;;\n"
                "    *'.State.Status'*) printf 'running\\n' ;;\n"
                "    *'.RestartCount'*) printf '0\\n' ;;\n"
                "    *) exit 1 ;;\n"
                "  esac\n"
                "  exit 0\n"
                "fi\n"
            )
            fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IEXEC)

            fake_python = temp_path / 'python3'
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf '%s\\n' \"$*\" >> \"${PYTHON_LOG}\"\n"
                "attempt=1\n"
                "if [ -f \"${PYTHON_ATTEMPTS}\" ]; then\n"
                "  attempt=$(( $(cat \"${PYTHON_ATTEMPTS}\") + 1 ))\n"
                "fi\n"
                "printf '%s' \"${attempt}\" > \"${PYTHON_ATTEMPTS}\"\n"
                "exit 0\n"
            )
            fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            env.update(
                {
                    'DEPLOY_ENV_FILE': str(temp_path / '.missing-deploy.env'),
                    'PHASE_BIN': 'true',
                    'COMMAND_LOG': str(command_log),
                    'DOCKER_LOG': str(docker_log),
                    'PYTHON_BIN': str(fake_python),
                    'PYTHON_LOG': str(python_log),
                    'PYTHON_ATTEMPTS': str(python_attempts),
                    'PATH': f"{temp_path}:{env['PATH']}",
                    'SECRET_KEY': 'test-secret',
                    'RENDER_EXTERNAL_HOSTNAME': 'invoices.ultramac.work',
                    'IMAGE': 'registry.example.com/lifeisgoodlabs/invoices',
                    'SHA_TAG': 'abc1234',
                    'WEB_VERIFY_ATTEMPTS': '1',
                    'WEB_VERIFY_DELAY_SECONDS': '0',
                }
            )

            result = subprocess.run(
                [str(deploy_copy)],
                cwd=temp_path,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                command_log.read_text().splitlines(),
                ['build project=03-invoices image=registry.example.com/lifeisgoodlabs/invoices:abc1234'],
            )
            self.assertEqual(
                docker_log.read_text().splitlines(),
                [
                    'project=03-invoices command=compose pull web scheduler',
                    'project=03-invoices command=compose up -d web',
                    'project=03-invoices command=compose up -d scheduler',
                    'project=03-invoices command=compose ps --services --status running web',
                    'project=03-invoices command=compose ps -q web',
                    'project=03-invoices command=inspect -f {{ index .Config.Labels "com.docker.compose.project" }} container-web',
                    'project=03-invoices command=inspect -f {{ .Name }} container-web',
                    'project=03-invoices command=inspect -f {{ .State.Status }} container-web',
                    'project=03-invoices command=inspect -f {{ .RestartCount }} container-web',
                    'project=03-invoices command=compose ps --services --status running scheduler',
                    'project=03-invoices command=compose ps -q scheduler',
                    'project=03-invoices command=inspect -f {{ index .Config.Labels "com.docker.compose.project" }} container-scheduler',
                    'project=03-invoices command=inspect -f {{ .Name }} container-scheduler',
                    'project=03-invoices command=inspect -f {{ .State.Status }} container-scheduler',
                    'project=03-invoices command=inspect -f {{ .RestartCount }} container-scheduler',
                    'project=03-invoices command=compose logs --no-color --tail 50 scheduler',
                ],
            )
            self.assertEqual(
                python_log.read_text().splitlines(),
                ['- http://127.0.0.1:8000/ invoices.ultramac.work'],
            )
            self.assertEqual(python_attempts.read_text(), '1')

    def test_docker_compose_preserves_shared_ultramac_mounts(self):
        compose_text = (ROOT / 'docker-compose.yml').read_text()

        self.assertIn('x-app-service: &app-service', compose_text)
        self.assertIn('web:\n    <<: *app-service', compose_text)
        self.assertIn('scheduler:\n    <<: *app-service', compose_text)

        volumes_block = re.search(
            r'volumes:\n(?P<entries>(?:\s+- .*\n)+)',
            compose_text,
        )

        self.assertIsNotNone(volumes_block)
        volume_entries = volumes_block.group('entries')
        self.assertIn('- ./db:/app/db', volume_entries)
        self.assertIn('- ./media:/app/media', volume_entries)
        self.assertIn('- ./.env:/app/.env:ro', volume_entries)

    def test_verify_deploy_script_checks_canonical_stack_and_both_services(self):
        verify_script = ROOT / 'scripts' / 'verify_deploy.sh'

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            docker_log = temp_path / 'docker.log'
            python_log = temp_path / 'python.log'
            python_attempts = temp_path / 'python-attempts.txt'
            fake_docker = temp_path / 'docker'
            fake_python = temp_path / 'python'

            fake_docker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf '%s\\n' \"$*\" >> \"${DOCKER_LOG}\"\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = ps ] && [ \"$3\" = --services ] && [ \"$4\" = --status ] && [ \"$5\" = running ]; then\n"
                "  printf '%s\\n' \"$6\"\n"
                "  exit 0\n"
                "fi\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = logs ] && [ \"$3\" = --no-color ] && [ \"$4\" = --tail ]; then\n"
                "  printf 'Scheduler tick completed without startup errors\\n'\n"
                "  exit 0\n"
                "fi\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = ps ] && [ \"$3\" = -q ]; then\n"
                "  printf 'container-%s\\n' \"$4\"\n"
                "  exit 0\n"
                "fi\n"
                "if [ \"$1\" = inspect ] && [ \"$2\" = -f ]; then\n"
                "  case \"$3\" in\n"
                "    *com.docker.compose.project*) printf '%s\\n' \"${COMPOSE_PROJECT_NAME}\" ;;\n"
                "    *'.Name'*) printf '/%s\\n' \"${COMPOSE_PROJECT_NAME}-${4#container-}-1\" ;;\n"
                "    *'.State.Status'*) printf 'running\\n' ;;\n"
                "    *'.RestartCount'*) printf '0\\n' ;;\n"
                "    *) exit 1 ;;\n"
                "  esac\n"
                "  exit 0\n"
                "fi\n"
                "exit 1\n"
            )
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf '%s\\n' \"$*\" >> \"${PYTHON_LOG}\"\n"
                "attempt=1\n"
                "if [ -f \"${PYTHON_ATTEMPTS}\" ]; then\n"
                "  attempt=$(( $(cat \"${PYTHON_ATTEMPTS}\") + 1 ))\n"
                "fi\n"
                "printf '%s' \"${attempt}\" > \"${PYTHON_ATTEMPTS}\"\n"
                "if [ \"${attempt}\" -lt 2 ]; then\n"
                "  exit 1\n"
                "fi\n"
                "exit 0\n"
            )
            fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IEXEC)
            fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            env.update(
                {
                    'COMPOSE_PROJECT_NAME': '03-invoices',
                    'DOCKER_BIN': str(fake_docker),
                    'PYTHON_BIN': str(fake_python),
                    'DOCKER_LOG': str(docker_log),
                    'PYTHON_LOG': str(python_log),
                    'PYTHON_ATTEMPTS': str(python_attempts),
                    'RENDER_EXTERNAL_HOSTNAME': 'invoices.ultramac.work',
                    'WEB_VERIFY_ATTEMPTS': '2',
                    'WEB_VERIFY_DELAY_SECONDS': '0',
                }
            )

            result = subprocess.run(
                [str(verify_script)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                docker_log.read_text().splitlines(),
                [
                    'compose ps --services --status running web',
                    'compose ps -q web',
                    'inspect -f {{ index .Config.Labels "com.docker.compose.project" }} container-web',
                    'inspect -f {{ .Name }} container-web',
                    'inspect -f {{ .State.Status }} container-web',
                    'inspect -f {{ .RestartCount }} container-web',
                    'compose ps --services --status running scheduler',
                    'compose ps -q scheduler',
                    'inspect -f {{ index .Config.Labels "com.docker.compose.project" }} container-scheduler',
                    'inspect -f {{ .Name }} container-scheduler',
                    'inspect -f {{ .State.Status }} container-scheduler',
                    'inspect -f {{ .RestartCount }} container-scheduler',
                    'compose logs --no-color --tail 50 scheduler',
                ],
            )
            self.assertEqual(
                python_log.read_text().splitlines(),
                [
                    '- http://127.0.0.1:8000/ invoices.ultramac.work',
                    '- http://127.0.0.1:8000/ invoices.ultramac.work',
                ],
            )
            self.assertEqual(python_attempts.read_text(), '2')

    def test_verify_deploy_script_resolves_host_from_runtime_env_file(self):
        verify_script = ROOT / 'scripts' / 'verify_deploy.sh'

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            runtime_env_file = temp_path / '.env'
            runtime_env_file.write_text('DEBUG=0\nRENDER_EXTERNAL_HOSTNAME=invoices.ultramac.work\n')
            docker_log = temp_path / 'docker.log'
            python_log = temp_path / 'python.log'
            fake_docker = temp_path / 'docker'
            fake_python = temp_path / 'python'

            fake_docker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf '%s\n' \"$*\" >> \"${DOCKER_LOG}\"\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = ps ] && [ \"$3\" = --services ] && [ \"$4\" = --status ] && [ \"$5\" = running ]; then printf '%s\\n' \"$6\"; exit 0; fi\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = logs ]; then printf 'Scheduler healthy\\n'; exit 0; fi\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = ps ] && [ \"$3\" = -q ]; then printf 'container-%s\\n' \"$4\"; exit 0; fi\n"
                "if [ \"$1\" = inspect ] && [ \"$2\" = -f ]; then\n"
                "  case \"$3\" in *com.docker.compose.project*) printf '%s\\n' \"${COMPOSE_PROJECT_NAME}\" ;; *'.Name'*) printf '/%s\\n' \"${COMPOSE_PROJECT_NAME}-${4#container-}-1\" ;; *'.State.Status'*) printf 'running\\n' ;; *'.RestartCount'*) printf '0\\n' ;; *) exit 1 ;; esac; exit 0\n"
                "fi\n"
                "exit 1\n"
            )
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf '%s\n' \"$*\" >> \"${PYTHON_LOG}\"\n"
                "test \"${3:-}\" = invoices.ultramac.work\n"
            )
            fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IEXEC)
            fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            env.pop('RENDER_EXTERNAL_HOSTNAME', None)
            env.update(
                {
                    'COMPOSE_PROJECT_NAME': '03-invoices',
                    'DOCKER_BIN': str(fake_docker),
                    'PYTHON_BIN': str(fake_python),
                    'DOCKER_LOG': str(docker_log),
                    'PYTHON_LOG': str(python_log),
                    'RUNTIME_ENV_FILE': str(runtime_env_file),
                    'WEB_VERIFY_ATTEMPTS': '1',
                    'WEB_VERIFY_DELAY_SECONDS': '0',
                }
            )

            result = subprocess.run(
                [str(verify_script)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                python_log.read_text().splitlines(),
                ['- http://127.0.0.1:8000/ invoices.ultramac.work'],
            )

    def test_verify_deploy_script_fails_when_configured_host_is_rejected(self):
        verify_script = ROOT / 'scripts' / 'verify_deploy.sh'

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_docker = temp_path / 'docker'
            fake_python = temp_path / 'python'

            fake_docker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = ps ] && [ \"$3\" = --services ] && [ \"$4\" = --status ] && [ \"$5\" = running ]; then printf '%s\\n' \"$6\"; exit 0; fi\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = logs ]; then printf 'Scheduler healthy\\n'; exit 0; fi\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = ps ] && [ \"$3\" = -q ]; then printf 'container-%s\\n' \"$4\"; exit 0; fi\n"
                "if [ \"$1\" = inspect ] && [ \"$2\" = -f ]; then\n"
                "  case \"$3\" in *com.docker.compose.project*) printf '%s\\n' \"${COMPOSE_PROJECT_NAME}\" ;; *'.Name'*) printf '/%s\\n' \"${COMPOSE_PROJECT_NAME}-${4#container-}-1\" ;; *'.State.Status'*) printf 'running\\n' ;; *'.RestartCount'*) printf '0\\n' ;; *) exit 1 ;; esac; exit 0\n"
                "fi\n"
                "exit 1\n"
            )
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "exit 1\n"
            )
            fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IEXEC)
            fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            env.update(
                {
                    'COMPOSE_PROJECT_NAME': '03-invoices',
                    'DOCKER_BIN': str(fake_docker),
                    'PYTHON_BIN': str(fake_python),
                    'WEB_VERIFY_HOST': 'invoices.ultramac.work',
                    'WEB_VERIFY_ATTEMPTS': '1',
                    'WEB_VERIFY_DELAY_SECONDS': '0',
                }
            )

            result = subprocess.run(
                [str(verify_script)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "Web verification failed for 'http://127.0.0.1:8000/' with Host 'invoices.ultramac.work' after 1 attempts.",
                result.stderr,
            )

    def test_verify_deploy_script_fails_when_scheduler_logs_show_startup_error(self):
        verify_script = ROOT / 'scripts' / 'verify_deploy.sh'

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_docker = temp_path / 'docker'
            fake_python = temp_path / 'python'

            fake_docker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = ps ] && [ \"$3\" = --services ] && [ \"$4\" = --status ] && [ \"$5\" = running ]; then\n"
                "  printf '%s\\n' \"$6\"\n"
                "  exit 0\n"
                "fi\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = ps ] && [ \"$3\" = -q ]; then\n"
                "  printf 'container-%s\\n' \"$4\"\n"
                "  exit 0\n"
                "fi\n"
                "if [ \"$1\" = compose ] && [ \"$2\" = logs ] && [ \"$3\" = --no-color ] && [ \"$4\" = --tail ]; then\n"
                "  printf 'Traceback (most recent call last):\\n'\n"
                "  exit 0\n"
                "fi\n"
                "if [ \"$1\" = inspect ] && [ \"$2\" = -f ]; then\n"
                "  case \"$3\" in\n"
                "    *com.docker.compose.project*) printf '%s\\n' \"${COMPOSE_PROJECT_NAME}\" ;;\n"
                "    *'.Name'*) printf '/%s\\n' \"${COMPOSE_PROJECT_NAME}-${4#container-}-1\" ;;\n"
                "    *'.State.Status'*) printf 'running\\n' ;;\n"
                "    *'.RestartCount'*) printf '0\\n' ;;\n"
                "    *) exit 1 ;;\n"
                "  esac\n"
                "  exit 0\n"
                "fi\n"
                "exit 1\n"
            )
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "exit 0\n"
            )
            fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IEXEC)
            fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            env.update(
                {
                    'COMPOSE_PROJECT_NAME': '03-invoices',
                    'DOCKER_BIN': str(fake_docker),
                    'PYTHON_BIN': str(fake_python),
                    'WEB_VERIFY_ATTEMPTS': '1',
                    'WEB_VERIFY_DELAY_SECONDS': '0',
                }
            )

            result = subprocess.run(
                [str(verify_script)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Scheduler logs contain a Python traceback after rollout.', result.stderr)

    def test_deployment_docs_match_canonical_rollout_and_verification_flow(self):
        readme_text = (ROOT / 'README.md').read_text()

        self.assertIn('`./scripts/deploy.sh` is the canonical live deployment entrypoint.', readme_text)
        self.assertIn('runs the tracked `docker compose` rollout for the canonical `03-invoices` stack', readme_text)
        self.assertIn('`03-invoices` as the canonical stack name', readme_text)
        self.assertIn('`03-invoices-web-1` and `03-invoices-scheduler-1`', readme_text)
        self.assertIn('should not require any separate manual container recreation commands', readme_text)
        self.assertIn('updates both services together under the same Compose project', readme_text)
        self.assertIn('exports `COMPOSE_PROJECT_NAME=03-invoices`', readme_text)
        self.assertIn('derives one `INVOICES_IMAGE` reference for both services', readme_text)
        self.assertIn('runs `docker compose pull web scheduler`', readme_text)
        self.assertIn('recreates `web` before `scheduler`', readme_text)
        self.assertIn('checks that both services are running under the same `03-invoices` Compose project', readme_text)
        self.assertIn('confirms the expected `03-invoices-web-1` and `03-invoices-scheduler-1` container names', readme_text)
        self.assertIn('verifies `http://127.0.0.1:8000/` responds successfully', readme_text)
        self.assertIn('fails if scheduler startup logs contain `Traceback (most recent call last):` or `Backup scheduler run failed:`', readme_text)
        self.assertIn('COMPOSE_PROJECT_NAME=03-invoices docker compose ps web scheduler', readme_text)
        self.assertIn('python3 -c', readme_text)
        self.assertIn('docker compose logs --no-color --tail 50 scheduler', readme_text)

    def test_project_readme_describes_canonical_live_rollout(self):
        project_readme_text = (ROOT / 'project' / 'README.md').read_text()

        self.assertIn(
            '`scripts/deploy.sh` is the canonical deployment entrypoint for the live `03-invoices` Compose rollout.',
            project_readme_text,
        )
        self.assertIn('refreshes the canonical `03-invoices` Compose stack', project_readme_text)
        self.assertIn('`03-invoices-web-1` and `03-invoices-scheduler-1`', project_readme_text)
        self.assertIn('without separate ad hoc container recreation steps', project_readme_text)
        self.assertIn('uses one `INVOICES_IMAGE` reference for both services', project_readme_text)
        self.assertIn('rolls `web` before `scheduler` under `03-invoices`', project_readme_text)
        self.assertIn('verify the named stack, expected container names, web health check, and scheduler startup logs', project_readme_text)

    def test_preview_script_uses_internal_backend_and_public_health_url(self):
        preview_common_text = (ROOT / 'scripts' / 'preview_common.sh').read_text()
        artifact_text = (ROOT / 'scripts' / 'artifact.sh').read_text()
        preview_text = (ROOT / 'scripts' / 'preview.sh').read_text()
        destroy_text = (ROOT / 'scripts' / 'destroy-preview.sh').read_text()

        self.assertIn('OPENCODE_PREVIEW_BACKEND_HOST:-host.docker.internal', preview_common_text)
        self.assertIn('preview_backend_host() {', preview_common_text)
        self.assertIn('OPENCODE_PREVIEW_ROLE:-current', preview_common_text)
        self.assertIn('OPENCODE_PREVIEW_REF', preview_common_text)
        self.assertIn("echo \"OPENCODE_PREVIEW_ROLE must be either 'current' or 'baseline'.\"", preview_common_text)
        self.assertIn("printf '%s/pr-%s%s-%s\\n' \"$(preview_runtime_root)\" \"${pr_number}\" \"${role_suffix}\" \"${project_key}\"", preview_common_text)
        self.assertIn("printf 'preview-pr-%s%s-%s\\n' \"${pr_number}\" \"${role_suffix}\" \"${project_key}\"", preview_common_text)
        self.assertIn("printf '1000\\n'", preview_common_text)
        self.assertIn('local port=$((20000 + pr_number + port_offset))', preview_common_text)
        self.assertIn("printf 'http://%s:%s\\n' \"$(preview_backend_host)\" \"$(preview_port)\"", preview_common_text)
        self.assertIn("printf 'https://%s\\n' \"$(preview_host)\"", preview_common_text)
        self.assertIn("printf '%s/accounts/login/\\n' \"$(public_preview_url)\"", preview_common_text)
        self.assertIn('git -C "${REPO_ROOT}" worktree add --force --detach "${source_root}" "${resolved_ref}"', preview_common_text)
        self.assertIn('git -C "${REPO_ROOT}" worktree remove --force "${source_root}"', preview_common_text)
        self.assertIn('SOURCE_ROOT="$(ensure_preview_source_root)"', artifact_text)
        self.assertIn('cd "${SOURCE_ROOT}"', artifact_text)
        self.assertIn('SOURCE_ROOT="$(ensure_preview_source_root)"', preview_text)
        self.assertIn('cd "${SOURCE_ROOT}"', preview_text)
        self.assertIn('PREVIEW_BACKEND_HOST="$(preview_backend_host)"', preview_text)
        self.assertIn('ALLOWED_HOSTS=127.0.0.1,localhost,${PREVIEW_HOST},${PREVIEW_BACKEND_HOST},.preview.ultramac.work', preview_text)
        self.assertIn('- "${PREVIEW_PORT}:8000"', preview_text)
        self.assertIn('remove_preview_source_root', destroy_text)

    def test_e2e_script_uses_resolved_python_for_preview_port_selection(self):
        e2e_text = (ROOT / 'scripts' / 'e2e.sh').read_text()

        self.assertIn('local python_bin', e2e_text)
        self.assertIn('python_bin="$(resolve_python_bin)"', e2e_text)
        self.assertIn('"${python_bin}" - <<\'PY\'', e2e_text)

    def test_demo_evidence_helper_accepts_visual_validation_checkpoint_mapping(self):
        helper_text = (ROOT / 'tests' / 'e2e' / 'helpers' / 'demo-evidence.js').read_text()

        self.assertIn('process.env.OPENCODE_DEMO_SCREENSHOT_CHECKPOINTS', helper_text)
        self.assertIn('process.env.OPENCODE_VISUAL_VALIDATION_FULL_PAGE_CHECKPOINTS', helper_text)
        self.assertIn('process.env.OPENCODE_EVIDENCE_SCREENSHOT_CHECKPOINTS', helper_text)
        self.assertIn('process.env.OPENCODE_EVIDENCE_SCREENSHOT_CHECKPOINTS_DIR', helper_text)
        self.assertIn('configured.set(name.trim(), checkpointPath.trim())', helper_text)

    def test_review_bot_workflow_uses_host_opencode_runtime(self):
        workflow_text = (ROOT / '.gitea' / 'workflows' / 'review-bot.yml').read_text()

        self.assertNotIn('OPENCODE_DEFAULT_MODEL:', workflow_text)
        self.assertNotIn('Install opencode CLI wrapper', workflow_text)
        self.assertNotIn('/usr/local/bin/opencode', workflow_text)
        self.assertIn('echo "/opt/homebrew/bin" >> "$GITHUB_PATH"', workflow_text)
        self.assertIn('echo "$HOST_HOME/.opencode/bin" >> "$GITHUB_PATH"', workflow_text)
        self.assertIn('export PATH="$HOST_HOME/.opencode/bin:/opt/homebrew/bin:$PATH"', workflow_text)
        self.assertIn('export PATH="$HOME/.opencode/bin:/opt/homebrew/bin:$PATH"', workflow_text)
        self.assertIn('source scripts/lib/python_runtime.sh', workflow_text)
        self.assertIn('opencode_export_python_bin', workflow_text)
        self.assertIn('which opencode', workflow_text)
        self.assertIn('opencode auth list', workflow_text)

    def test_opencode_wrapper_resolves_controller_checkout_cli(self):
        wrapper_path = ROOT / 'scripts' / 'opencode'

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            scripts_dir = temp_path / 'scripts'
            controller_bin_dir = temp_path / 'controller' / 'bin'
            scripts_dir.mkdir()
            controller_bin_dir.mkdir(parents=True)

            wrapper_copy = scripts_dir / 'opencode'
            wrapper_copy.write_text(wrapper_path.read_text())
            wrapper_copy.chmod(wrapper_copy.stat().st_mode | stat.S_IEXEC)

            fake_opencode = controller_bin_dir / 'opencode'
            fake_opencode.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf 'fake-opencode %s\\n' \"$*\"\n"
            )
            fake_opencode.chmod(fake_opencode.stat().st_mode | stat.S_IEXEC)

            resolve_result = subprocess.run(
                ['bash', str(wrapper_copy)],
                cwd=temp_path,
                env={**os.environ, 'OPENCODE_RESOLVE_ONLY': '1'},
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(resolve_result.returncode, 0, resolve_result.stderr)
            self.assertEqual(resolve_result.stdout.strip(), str(fake_opencode))

            exec_result = subprocess.run(
                ['bash', str(wrapper_copy), 'review', '--help'],
                cwd=temp_path,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(exec_result.returncode, 0, exec_result.stderr)
            self.assertEqual(exec_result.stdout.strip(), 'fake-opencode review --help')

    def test_opencode_wrapper_injects_default_model_when_not_explicitly_set(self):
        wrapper_path = ROOT / 'scripts' / 'opencode'

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            scripts_dir = temp_path / 'scripts'
            controller_bin_dir = temp_path / 'controller' / 'bin'
            scripts_dir.mkdir()
            controller_bin_dir.mkdir(parents=True)

            wrapper_copy = scripts_dir / 'opencode'
            wrapper_copy.write_text(wrapper_path.read_text())
            wrapper_copy.chmod(wrapper_copy.stat().st_mode | stat.S_IEXEC)

            fake_opencode = controller_bin_dir / 'opencode'
            fake_opencode.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf 'fake-opencode %s\\n' \"$*\"\n"
            )
            fake_opencode.chmod(fake_opencode.stat().st_mode | stat.S_IEXEC)

            injected_result = subprocess.run(
                ['bash', str(wrapper_copy), 'run', 'review this'],
                cwd=temp_path,
                env={**os.environ, 'OPENCODE_DEFAULT_MODEL': 'openai/gpt-5-codex'},
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(injected_result.returncode, 0, injected_result.stderr)
            self.assertEqual(
                injected_result.stdout.strip(),
                'fake-opencode --model openai/gpt-5-codex run review this',
            )

            explicit_result = subprocess.run(
                ['bash', str(wrapper_copy), '--model', 'openai/gpt-5.4', 'run', 'review this'],
                cwd=temp_path,
                env={**os.environ, 'OPENCODE_DEFAULT_MODEL': 'openai/gpt-5-codex'},
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(explicit_result.returncode, 0, explicit_result.stderr)
            self.assertEqual(
                explicit_result.stdout.strip(),
                'fake-opencode --model openai/gpt-5.4 run review this',
            )

    def test_issue_42_acceptance_criteria_have_repository_backed_evidence(self):
        deploy_script = (ROOT / 'scripts' / 'deploy.sh').read_text()
        verify_script = (ROOT / 'scripts' / 'verify_deploy.sh').read_text()
        compose_text = (ROOT / 'docker-compose.yml').read_text()
        readme_text = (ROOT / 'README.md').read_text()
        project_readme_text = (ROOT / 'project' / 'README.md').read_text()

        criteria_checks = {
            'canonical deployment command updates live deployment without undocumented manual recreation': [
                '`./scripts/deploy.sh` is the canonical live deployment entrypoint.',
                'should not require any separate manual container recreation commands',
            ],
            'live rollout updates both web and scheduler as one Docker Compose stack': [
                'docker compose pull web scheduler',
                'docker compose up -d web',
                'docker compose up -d scheduler',
            ],
            'operators have a short documented verification path for both services': [
                'COMPOSE_PROJECT_NAME=03-invoices docker compose ps web scheduler',
                'docker compose logs --no-color --tail 50 scheduler',
                'python3 -c',
            ],
            'deploy script performs tracked compose rollout after image publication': [
                '"${REPO_ROOT}/scripts/build_and_push.sh"',
                'docker compose up -d web',
                '"${REPO_ROOT}/scripts/verify_deploy.sh"',
            ],
            'tracked rollout uses stable explicit compose project name': [
                'export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-03-invoices}"',
                'name: ${COMPOSE_PROJECT_NAME:-03-invoices}',
            ],
            'live container names are predictable under the project name': [
                'expected_name="${COMPOSE_PROJECT_NAME}-${service}-1"',
                '`03-invoices-web-1` and `03-invoices-scheduler-1`',
            ],
            'compose configuration accepts one explicit image reference for both services': [
                'export INVOICES_IMAGE="${INVOICES_IMAGE:-${IMAGE}:${ROLLOUT_IMAGE_TAG}}"',
                'image: ${INVOICES_IMAGE:-${REGISTRY_IMAGE:-git.ultramac.work/lifeisgoodlabs/invoices}:latest}',
            ],
            'rollout preserves existing bind-mounted env db and media paths': [
                '- ./.env:/app/.env:ro',
                '- ./db:/app/db',
                '- ./media:/app/media',
            ],
            'rollout order minimizes scheduler startup races against migrations': [
                'docker compose up -d web',
                'docker compose up -d scheduler',
                'recreates `web` before `scheduler`',
            ],
            'repository deployment docs match tracked rollout behavior': [
                'runs the tracked `docker compose` rollout for the canonical `03-invoices` stack',
                'refreshes the canonical `03-invoices` Compose stack',
            ],
            'canonical deploy path includes verification of both services after rollout': [
                '"${REPO_ROOT}/scripts/verify_deploy.sh"',
                'EXPECTED_SERVICES=(web scheduler)',
            ],
            'production rollout no longer depends on undocumented manual container handling': [
                'should not require any separate manual container recreation commands',
                'without separate ad hoc container recreation steps',
            ],
            'manual compose inspection commands resolve to the same named stack': [
                'COMPOSE_PROJECT_NAME=03-invoices docker compose ps',
                'COMPOSE_PROJECT_NAME=03-invoices docker compose logs web',
                'COMPOSE_PROJECT_NAME=03-invoices docker compose logs scheduler',
            ],
            'validation covers tracked rollout behavior for named stack and both services': [
                'def test_canonical_deploy_command_runs_full_rollout_and_verification_flow(self):',
                'def test_verify_deploy_script_checks_canonical_stack_and_both_services(self):',
            ],
            'validation confirms compose invocation targets 03-invoices consistently': [
                'project=03-invoices command=compose pull web scheduler',
                'project=03-invoices command=compose up -d scheduler',
            ],
            'validation confirms both services are recreated against intended image reference': [
                'build project=03-invoices image=registry.example.com/lifeisgoodlabs/invoices:abc1234',
                'verify_deploy.sh project=03-invoices image=registry.example.com/lifeisgoodlabs/invoices:abc1234',
            ],
            'validation confirms post-deploy verification checks web and scheduler startup state': [
                'compose logs --no-color --tail 50 scheduler',
                "['- http://127.0.0.1:8000/ invoices.ultramac.work']",
            ],
        }

        evidence_text = '\n'.join(
            [deploy_script, verify_script, compose_text, readme_text, project_readme_text, (ROOT / 'tests' / 'test_suite.py').read_text()]
        )

        for criterion, snippets in criteria_checks.items():
            with self.subTest(criterion=criterion):
                for snippet in snippets:
                    self.assertIn(snippet, evidence_text)

    def test_readme_lists_issue_42_acceptance_evidence_explicitly(self):
        readme_text = (ROOT / 'README.md').read_text()

        expected_lines = [
            'Issue 42 acceptance evidence is explicit in the tracked rollout and validation:',
            'Running the canonical deployment command updates the live invoices deployment without requiring undocumented manual container recreation commands',
            'The live rollout updates both `web` and `scheduler` as one Docker Compose stack',
            'Operators have a short documented verification path that confirms both services are healthy after rollout',
            '`scripts/deploy.sh` performs the tracked `docker compose` rollout step after image publication',
            'The tracked rollout uses a stable explicit Compose project name of `03-invoices` by default on Ultramac',
            'The resulting live container names are predictable under that project name, including `03-invoices-web-1` and `03-invoices-scheduler-1`',
            'The Compose configuration accepts an explicit image reference or tag so both services are recreated from the intended release image',
            'The rollout preserves the current bind-mounted `.env`, `db`, and `media` paths already used by the deployment',
            'The rollout order minimizes scheduler startup racing migrations by ensuring the web service performs migration-bearing startup before the scheduler is recreated or started',
            'Repository deployment docs match the actual tracked rollout behavior',
            'The canonical deploy path includes verification of both services after rollout',
            'The production rollout no longer depends on undocumented manual container handling',
            'Manual Compose inspection commands used during operations resolve to the same named stack as the tracked deploy flow',
            'Validation covers the tracked rollout script behavior for the named Compose stack and both services',
            'Validation confirms the compose invocation targets `03-invoices` consistently',
            'Validation confirms both services are recreated against the intended image reference during rollout logic or equivalent scripted verification',
            'Validation confirms post-deploy verification checks both web responsiveness and scheduler startup state',
        ]

        for expected_line in expected_lines:
            with self.subTest(expected_line=expected_line):
                self.assertIn(expected_line, readme_text)

    def test_project_form_regressions(self):
        if importlib.util.find_spec('django') is None:
            self.skipTest('django is not installed in this interpreter')

        env = os.environ.copy()
        env.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')

        result = subprocess.run(
            [
                sys.executable,
                'manage.py',
                'test',
                'invoices.tests.test_projects',
                '--verbosity',
                '0',
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        details = '\n'.join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        self.assertEqual(result.returncode, 0, details)

    def test_backup_execution_lock_path_is_explicit_for_web_and_scheduler(self):
        compose_text = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
        lock_setting = 'BACKUP_EXECUTION_LOCK_PATH=/app/media/.locks/backup-execution.lock'

        web_section = compose_text.split('  web:\n', 1)[1].split('\n  scheduler:\n', 1)[0]
        scheduler_section = compose_text.split('  scheduler:\n', 1)[1]

        self.assertIn(lock_setting, web_section)
        self.assertIn(lock_setting, scheduler_section)
