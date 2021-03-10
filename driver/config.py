import json
import os

import consts as Consts

CONFIG_PATH = '/config'
NVMESH_VERSION_FILE_PATH = '/opt/NVMesh/client-repo/version'
DRIVER_VERSION_FILE_PATH = '/version'

class ConfigError(Exception):
	pass

class Config(object):
	NVMESH_BIN_PATH = '/host/bin/'
	MANAGEMENT_SERVERS = None
	MANAGEMENT_PROTOCOL = None
	MANAGEMENT_USERNAME = None
	MANAGEMENT_PASSWORD = None
	SOCKET_PATH = None
	DRIVER_NAME = None
	ATTACH_IO_ENABLED_TIMEOUT = None
	PRINT_STACK_TRACES = None
	DRIVER_VERSION = None
	NVMESH_VERSION_INFO = None
	TOPOLOGY_TYPE = None
	TOPOLOGY = None

class Parsers(object):
	@staticmethod
	def parse_boolean(stringValue):
		if stringValue.lower() == 'true':
			return True
		elif stringValue.lower() == 'false':
			return False
		else:
			raise ValueError('Could not parse boolean from {}'.format(stringValue))


def _read_file_contents(filename):
	with open(filename) as fp:
		return fp.read()

def _get_config_map_param(name, default=None):
	value = None
	try:
		value = _read_file_contents(CONFIG_PATH + '/' + name)
	except IOError:
		pass

	return value or default

def _read_bash_file(filename):
	g = {}
	l = {}

	if os.path.exists(filename):
		execfile(filename, g, l)

	return l

def _get_env_var(key, default=None, parser=None):
	if key in os.environ:
		if parser:
			try:
				return parser(os.environ[key])
			except ValueError as ex:
				raise ConfigError('Error parsing value for {key}. Error: {msg}'.format(key=key, msg=ex.message))
		else:
			return os.environ[key]
	else:
		return default

def print_config():
	asDict = dict(vars(Config))
	params = {}
	for key in asDict.keys():
		if not key.startswith('_'):
			params[key] = asDict[key]

	print('Config=%s' % json.dumps(params, indent=4))

class ConfigLoader(object):
	def load(self):
		Config.MANAGEMENT_SERVERS = _get_config_map_param('management.servers') or _get_env_var('MANAGEMENT_SERVERS')
		Config.MANAGEMENT_PROTOCOL = _get_config_map_param('management.protocol') or _get_env_var('MANAGEMENT_SERVERS', default='https')
		Config.MANAGEMENT_USERNAME = _get_env_var('MANAGEMENT_USERNAME', default='admin@excelero.com')
		Config.MANAGEMENT_PASSWORD = _get_env_var('MANAGEMENT_PASSWORD', default='admin')
		Config.SOCKET_PATH = _get_env_var('SOCKET_PATH', default=Consts.DEFAULT_UDS_PATH)
		Config.DRIVER_NAME = _get_env_var('DRIVER_NAME', default=Consts.DEFAULT_DRIVER_NAME)

		Config.DRIVER_VERSION = _read_file_contents(DRIVER_VERSION_FILE_PATH)
		Config.NVMESH_VERSION_INFO = _read_bash_file(NVMESH_VERSION_FILE_PATH)

		Config.ATTACH_IO_ENABLED_TIMEOUT = int(_get_config_map_param('attachIOEnabledTimeout', default=30))
		Config.PRINT_STACK_TRACES = _get_config_map_param('printStackTraces', default=False)
		Config.TOPOLOGY = _get_config_map_param('topology', default=None)

		ConfigValidator().validate()
		print("Loaded Config with SOCKET_PATH={}, MANAGEMENT_SERVERS={}, DRIVER_NAME={}".format(Config.SOCKET_PATH, Config.MANAGEMENT_SERVERS, Config.DRIVER_NAME))

class ConfigValidator(object):
	def validate(self):
		if Config.TOPOLOGY:
			if Config.MANAGEMENT_SERVERS:
				print("WARNING: MANAGEMENT_SERVERS env variable has no effect when multipleNVMeshBackends is set to True")
		else:
			if not Config.MANAGEMENT_SERVERS:
				raise ConfigError("MANAGEMENT_SERVERS environment variable not found or is empty")

		if Config.TOPOLOGY:
			try:
				Config.TOPOLOGY = json.loads(Config.TOPOLOGY)
			except ValueError as ex:
				raise ConfigError('Failed to parse config.topology. Error %s. originalValue:\n%s' % (ex, Config.TOPOLOGY))

		self.validate_topology()

	def validate_topology(self):
		if not Config.TOPOLOGY:
			Config.TOPOLOGY_TYPE = Consts.TopologyType.SINGLE_ZONE_CLUSTER
			return

		supportedTopologyTypes = [
			# The driver should handle each supported topology type in node_service.NodeGetInfo and controller_service.CreateVolume
			Consts.TopologyType.MULTIPLE_NVMESH_CLUSTERS
		]

		topology_conf = Config.TOPOLOGY
		Config.TOPOLOGY_TYPE = topology_conf.get('type', Consts.TopologyType.MULTIPLE_NVMESH_CLUSTERS)

		if Config.TOPOLOGY_TYPE not in supportedTopologyTypes:
			raise ConfigError('Unsupported topologyType %s' % Config.TOPOLOGY_TYPE)

		if "zoneSelectionPolicy" not in topology_conf:
			topology_conf["zoneSelectionPolicy"] = Consts.ZoneSelectionPolicy.RANDOM

		if "zones" not in topology_conf:
			raise ConfigError('Missing "zones" key in ConfigMap.topology')

		zones = topology_conf["zones"]
		if not isinstance(zones, dict):
			raise ConfigError('Expected "zones" key in ConfigMap.topology to be a dict, but received %s' % type(zones))

		for zone_name, zone_data in zones.items():
			if "nodes" not in zone_data:
				raise ConfigError('Missing "nodes" key in ConfigMap.topology in zone %s' % zone_name)

config_loader = ConfigLoader()
