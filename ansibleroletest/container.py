from __future__ import unicode_literals
from __future__ import absolute_import

import urlparse

OOMKilled, Dead, Paused, Running, Restarting, Stopped = range(1, 7)


class Container(object):
    def __init__(self, client, image, detach=True, **options):
        self._client = client
        self._props = {
            'image': image,
            'detach': detach
        }
        self._props.update(options)
        self._host_ip = None
        self._inspected = False

    @property
    def host_ip(self):
        if self._client.base_url.startswith('unix://'):
            return '0.0.0.0'

        if not self._host_ip:
            o = urlparse.urlparse(self._client.base_url)
            self._host_ip = o.hostname

        return self._host_ip

    @property
    def id(self):
        if 'id' not in self._props:
            return None
        return self._props['id']

    @property
    def image(self):
        return self._props['image']

    @property
    def internal_ip(self):
        return self.inspect()['NetworkSettings']['IPAddress']

    @property
    def state(self):
        state_info = self.inspect()['State']
        state = {
            'status': Stopped,
            'pid': state_info['Pid'],
            'started_at': state_info['StartedAt'],
            'finished_at': state_info['FinishedAt'],
            'exit_code': state_info['ExitCode'],
            'error': state_info['Error']
        }
        if state_info['OOMKilled']:
            state['status'] = OOMKilled
        if state_info['Dead']:
            state['status'] = Dead
        if state_info['Paused']:
            state['status'] = Paused
        if state_info['Running']:
            state['status'] = Running
        if state_info['Restarting']:
            state['status'] = Restarting
        return state

    def create(self, **options):
        self._props.update(options)
        res = self._client.create_container(**self._props)
        self._props['id'] = res['Id']
        return res['Id']

    def destroy(self, **options):
        if not self.id:
            return
        if self.state['status'] is Running:
            self.stop()
        self._client.remove_container(container=self.id, **options)

    def execute(self, cmd, **options):
        res = self._client.exec_create(container=self.id, cmd=cmd,
                                       **options)
        out = self._client.exec_start(exec_id=res['Id'])
        return out, self._client.exec_inspect(exec_id=res['Id'])

    def inspect(self, update=False):
        if update:
            self._inspected = False
        if not self._inspected:
            self._inspected = self._client.inspect_container(container=self.id)
        return self._inspected

    def port(self, port):
        res = self._client.port(self.id, port)
        if not res:
            return None
        return self.host_ip, res[0]['HostPort']

    def remove(self, **options):
        self._client.remove_container(container=self.id, **options)

    def start(self, **options):
        if not self.id:
            self.create()

        options['container'] = self.id
        self._client.start(**options)
        self._inspected = False

    def stream(self, cmd, **options):
        res = self._client.exec_create(container=self.id, cmd=cmd,
                                       **options)
        out = self._client.exec_start(exec_id=res['Id'], stream=True)
        for line in out:
            yield line
        yield self._client.exec_inspect(exec_id=res['Id'])

    def stop(self):
        self._client.stop(container=self.id)
        self._inspected = False

    def wait(self):
        return self._client.wait(container=self.id)


class ContainerManager(object):
    def __init__(self, docker):
        self._docker = docker
        self._containers = {}

    @property
    def containers(self):
        return self._containers

    def create(self, name, **options):
        self._containers[name] = Container(self._docker, **options)
        return self._containers[name]

    def destroy(self, names=None):
        if not names:
            names = []
        if not isinstance(names, list):
            names = [names]
        for name, container in self._containers.copy().iteritems():
            if not names or name in names:
                container.destroy()
                del self._containers[name]