"""Independent production control ownership, private transport and durable state."""
import os
import time
from pathlib import Path
from modal_config import exclude_upload
from modal_control import SECRET_KEYS

def _secret_put(name: str, data: dict) -> None:
    """Create-or-replace a Modal Secret across old/new CLI APIs.

    Newer modal versions dropped the name kwarg from Secret.from_dict and have
    no update endpoint, so rotation means delete-by-name then create-by-name.
    """
    import modal
    from modal.secret import SecretManager
    manager = SecretManager(client=modal.client.Client.from_config())
    try:
        manager.delete(name, allow_missing=True)
    except Exception as error:  # noqa: BLE001 - tolerate unknown secret states
        print(f"[secret] delete skipped ({type(error).__name__})")
    manager.create(name, data)


OWNER = 'dark-champion-control'
NAME = 'runtime'

def control_image(root):
    import modal
    return (modal.Image.from_registry('ubuntu:24.04')
        .env({'DEBIAN_FRONTEND':'noninteractive',
              'PYTHONPATH':'/app/dark-champion/scripts', 'MODAL_PERSISTENT_CONTROL':'true'})
        .apt_install('docker.io','docker-compose-v2','openssh-server','python3',
                     'python3-yaml','python3-httpx','curl')
        .add_local_dir(root,'/app/dark-champion',copy=True,ignore=exclude_upload))

def command(sandbox, *args):
    process = sandbox.exec(*args)
    output, error = process.stdout.read(), process.stderr.read()
    process.wait()
    if process.returncode:
        raise RuntimeError('Control command failed: ' + error[-1000:])
    return output.strip()

def exists(sandbox, path):
    process = sandbox.exec('test','-f',path)
    process.wait()
    return process.returncode == 0

def route(sandbox):
    host_key = command(sandbox,'cat','/etc/ssh/ssh_host_ed25519_key.pub')
    host, port = sandbox.tunnels()[22].tcp_socket
    crawler = command(sandbox,'docker','inspect','dark-modal-crawl4ai-1','--format',
                      '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
    return {'host':host,'port':port,'host_key':host_key,'crawler_host':crawler}

def desktop_route(sandbox):
    """One authenticated SSH session plus a dynamic SOCKS proxy for the desktop."""
    host_key = command(sandbox,'cat','/etc/ssh/ssh_host_ed25519_key.pub')
    host, port = sandbox.tunnels()[22].tcp_socket
    return {'tunnel':True,'host':host,'port':port,'host_key':host_key}

def ensure_control(root, *, desktop=False):
    import modal
    from release_manifest import source_hash
    expected = source_hash()
    # This stable owner app is not replaced when the GPU deployment is updated.
    owner = modal.App.lookup(OWNER,create_if_missing=True)
    state = modal.Volume.from_name('dark-champion-runtime-state-v2',
                                   create_if_missing=True,version=2)
    values = {key:os.environ[key] for key in SECRET_KEYS}
    public = os.environ['MODAL_CONTROL_PUBLIC_KEY']
    resolver = desktop_route if desktop else route
    deadline = time.monotonic()+1200
    sandbox = None
    while time.monotonic()<deadline:
        if sandbox is None:
            try:
                sandbox = modal.Sandbox.from_name(OWNER,NAME)
            except modal.exception.NotFoundError:
                try:
                    sandbox = modal.Sandbox.create('python3',
                        '/app/dark-champion/scripts/modal_control.py',app=owner,name=NAME,
                        image=control_image(root),runtime='vm',cpu=4,memory=8192,timeout=5400,
                        volumes={'/state':state},unencrypted_ports=[22],
                        secrets=[modal.Secret.from_dict({**values,'MODAL_CONTROL_PUBLIC_KEY':public})])
                except modal.exception.AlreadyExistsError:
                    # Atomic sandbox naming prevents a second database writer.
                    time.sleep(2)
                    continue
        status = sandbox.poll()
        if status is not None:
            if status != 0:
                detail = sandbox.stderr.read()[-4000:] + sandbox.stdout.read()[-4000:]
                for value in values.values(): detail = detail.replace(value,'[REDACTED]')
                raise RuntimeError('Production control bootstrap failed: ' + detail)
            sandbox = None
            time.sleep(2)
            continue
        if exists(sandbox,'/app/dark-champion/.run/control-closing'):
            time.sleep(2)
            continue
        if exists(sandbox,'/app/dark-champion/.run/control-ready'):
            revision = command(sandbox,'cat','/app/dark-champion/.run/control-source')
            if revision == expected:
                return sandbox,resolver(sandbox)
            # Flush the previous revision before allowing its successor to mount data.
            command(sandbox,'touch','/app/dark-champion/.run/stop-control')
            time.sleep(2)
            continue
        time.sleep(3)
    raise TimeoutError('Private persistent control readiness deadline')
