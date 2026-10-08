"""Bounded Modal control VM and pinned SSH transport; no public auxiliary ports."""
import json
import ipaddress
import os
from pathlib import Path
import socket
import subprocess
import time
import signal

PORTS = {'REDIS': 6379, 'QDRANT': 6333, 'SEARXNG': 8080,
         'CRAWL4AI': 11235, 'SANDBOX': 8091, 'OPEN_WEBUI': 3000}
SECRET_KEYS = ('DARK_API_KEY', 'VLLM_API_KEY', 'SANDBOX_API_KEY',
               'CRAWL4AI_API_TOKEN', 'WEBUI_SECRET_KEY', 'SEARXNG_SECRET')

def persistent_config(data, state):
    """One control VM owns all database files on a real mounted Volume."""
    state = Path(state)
    if state != Path('/state') or not state.is_mount():
        raise ValueError('Persistent control requires the mounted /state Volume')
    for name, destination in (('redis', '/data'), ('qdrant', '/qdrant/storage'),
                              ('open-webui', '/app/backend/data')):
        directory = state / name
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        data['services'][name]['volumes'] = [str(directory) + ':' + destination]
    return data

def authenticated_transport(master):
    """Count authenticated root sessions owned by this SSH daemon."""
    if master.poll() is not None:
        raise RuntimeError('Owned control SSH daemon exited')
    result = subprocess.run(['ps', '-eo', 'pid=,ppid=,args='],
                            text=True, capture_output=True, check=True)
    rows = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) == 3:
            rows.append((int(fields[0]), int(fields[1]), fields[2]))
    descendants = {master.pid}
    while True:
        children = {pid for pid, parent, _ in rows if parent in descendants}
        expanded = descendants | children
        if expanded == descendants: break
        descendants = expanded
    # OpenSSH titles the authenticated -N tunnel "sshd: root" (without
    # @notty). Exclude pre-auth [priv] workers and unrelated process arguments.
    return any(pid in descendants and (args == 'sshd: root' or args.startswith('sshd: root@'))
               for pid, _, args in rows)

def local_keys(root):
    from runtime_config import read_env
    values = read_env(root / '.env')
    secrets = {key: values[key] for key in SECRET_KEYS}
    if any(not v or v == 'generated-by-bootstrap' for v in secrets.values()):
        raise ValueError('Run bootstrap_env.py before Modal validation')
    key = root / '.run' / 'modal-control-key'
    key.parent.mkdir(exist_ok=True)
    if not key.exists():
        subprocess.run(['ssh-keygen', '-t', 'ed25519', '-N', '', '-f', str(key)],
                       check=True, stdout=subprocess.DEVNULL, timeout=30)
        key.chmod(0o600)
    return secrets, key.read_text(), Path(str(key) + '.pub').read_text()

def start_forwarder(env, route, root):
    """SSH host key comes from authenticated Modal exec, never ssh-keyscan/TOFU."""
    host, port = route['host'], int(route['port'])
    if not host or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for c in host):
        raise ValueError('Invalid SSH tunnel host')
    if not 1 <= port <= 65535 or not route['host_key'].startswith('ssh-ed25519 '):
        raise ValueError('Missing pinned SSH identity')
    crawler = ipaddress.IPv4Address(route.get('crawler_host', '127.0.0.1'))
    if not crawler.is_private or crawler.is_link_local or crawler.is_unspecified or crawler.is_multicast:
        raise ValueError('Crawler target must be a private container address')
    directory = root / '.run' / 'ssh'
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    private = directory / 'identity'
    private.write_text(env['MODAL_CONTROL_PRIVATE_KEY']); private.chmod(0o600)
    known = directory / 'known_hosts'
    known.write_text(f"[{host}]:{port} {route['host_key'].strip()}\n"); known.chmod(0o600)
    args = ['ssh', '-N', '-T', '-p', str(port), '-i', str(private),
            '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', f'UserKnownHostsFile={known}',
            '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15',
            '-o', 'ServerAliveCountMax=2', '-o', 'ConnectTimeout=20']
    for name, p in PORTS.items():
        target = str(crawler) if name == 'CRAWL4AI' else '127.0.0.1'
        args += ['-L', f'127.0.0.1:{p}:{target}:{p}']
    args += ['-R', '127.0.0.1:8088:127.0.0.1:8088', 'root@' + host]
    log = (directory / 'transport.log').open('ab')
    try: process = subprocess.Popen(args, stdout=log, stderr=log, start_new_session=True)
    finally: log.close()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Pinned SSH transport exited; inspect transport.log')
        try:
            with socket.create_connection(('127.0.0.1', 6379), timeout=1): break
        except OSError: time.sleep(.2)
    else:
        process.terminate(); process.wait(timeout=5)
        raise TimeoutError('SSH forwarding startup timeout')
    for name, p in PORTS.items():
        env[name + '_EXTERNAL_URL'] = ('redis' if name == 'REDIS' else 'http') + f'://127.0.0.1:{p}' + ('/0' if name == 'REDIS' else '')
    return process

def vm_bootstrap():
    """Executed inside the trusted CPU VM, prior to GPU allocation."""
    import yaml
    root = Path('/app/dark-champion')
    os.chdir(root)
    os.umask(0o077)
    persistent = os.getenv('MODAL_PERSISTENT_CONTROL') == 'true'
    ssh = Path('/root/.ssh'); ssh.mkdir(exist_ok=True); ssh.chmod(0o700)
    (ssh / 'authorized_keys').write_text(os.environ['MODAL_CONTROL_PUBLIC_KEY'] + '\n')
    Path('/run/sshd').mkdir(exist_ok=True)
    subprocess.run(['ssh-keygen', '-A'], check=True, stdout=subprocess.DEVNULL)
    config = '/etc/ssh/sshd_config.d/dark-champion.conf'
    Path(config).write_text('PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin prohibit-password\nGatewayPorts no\nAllowTcpForwarding yes\nAllowAgentForwarding no\nX11Forwarding no\nPermitTunnel no\n')
    ssh_server = subprocess.Popen(['/usr/sbin/sshd', '-D']) if persistent else None
    if not persistent: subprocess.run(['/usr/sbin/sshd'], check=True)
    daemon = subprocess.Popen(['dockerd'], stdout=Path('/tmp/dockerd.log').open('wb'), stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if daemon.poll() is not None: raise RuntimeError('dockerd exited; inspect /tmp/dockerd.log')
        if subprocess.run(['docker', 'info'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0: break
        time.sleep(1)
    else: raise TimeoutError('Docker startup')
    from service_manager import auxiliary_config
    env = dict(os.environ)
    (root / '.env').write_text('\n'.join(key + '=' + env[key] for key in SECRET_KEYS) + '\n')
    data = auxiliary_config(env)
    if persistent: data = persistent_config(data, '/state')
    # Internal crawler keeps its networkless extraction network and Docker limits.
    (root / '.run').mkdir(exist_ok=True)
    compose = root / '.run' / 'auxiliary.yml'
    compose.write_text(yaml.safe_dump(data, sort_keys=False))
    command = ['docker', 'compose', '-p', 'dark-modal', '-f', str(compose)]
    subprocess.run(command + ['build', 'sandbox-runtime', 'sandbox-broker', 'crawl4ai'], check=True)
    subprocess.run(command + ['up', '-d'], check=True)
    if persistent:
        from release_manifest import source_hash
        (root / '.run/control-source').write_text(source_hash())
    # No auxiliary listener is exposed through Modal; only authenticated SSH is tunneled.
    (root / '.run' / 'control-ready').write_text('ready\n')
    if persistent:
        stopping = False
        def request_stop(*_):
            nonlocal stopping
            stopping = True
        signal.signal(signal.SIGTERM, request_stop)
        last_transport = time.monotonic()
        try:
            while daemon.poll() is None:
                if authenticated_transport(ssh_server): last_transport = time.monotonic()
                if stopping or (root / '.run/stop-control').exists() or time.monotonic() - last_transport > 120:
                    (root / '.run/control-closing').write_text('closing\n')
                    subprocess.run(command + ['stop', '--timeout', '30'], check=True, timeout=90)
                    Path('/state/control-shutdown.json').write_text(json.dumps({
                        'databases_stopped': True, 'timestamp': time.time()}))
                    subprocess.run(['sync', '/state'], check=True, timeout=60)
                    (root / '.run/control-clean').write_text('synced\n')
                    return
                time.sleep(5)
            raise RuntimeError('Docker control daemon terminated')
        finally:
            ssh_server.terminate()
            ssh_server.wait(timeout=10)
            if daemon.poll() is None:
                daemon.terminate()
                daemon.wait(timeout=15)
    while daemon.poll() is None: time.sleep(5)
    raise RuntimeError('Docker control daemon terminated')

if __name__ == '__main__': vm_bootstrap()
