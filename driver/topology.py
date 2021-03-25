import Queue
import random

from grpc import StatusCode

import consts
from common import DriverError
from config import Config
from sdk_helper import NVMeshSDKHelper


class TopologyUtils(object):
	@staticmethod
	def get_zone_info(zone):
		zone_info = Config.TOPOLOGY['zones'].get(zone)

		if not zone_info:
			raise ValueError('Zone %s missing from Config.topology' % zone)

		return zone_info

	@staticmethod
	def get_management_info_from_zone(zone):
		zone_info = TopologyUtils.get_zone_info(zone)

		mgmt_info = zone_info.get('management')
		if not mgmt_info:
			raise ValueError('Zone {0} missing mgmt_info in Config.topology.zones.{0}'.format(zone))

		return mgmt_info

	@staticmethod
	def get_node_zone(node_id, logger):
		logger.debug('Looking for node {} in all management servers'.format(node_id))
		all_zones = Config.TOPOLOGY.get('zones').items()
		for zone_name, zone_data in all_zones:
			api_params = TopologyUtils.get_api_params(logger, zone_name)
			is_in_zone = NVMeshSDKHelper.check_if_node_in_management(node_id, api_params, logger)
			if is_in_zone:
				logger.info('Node {} found on management server {}. settings zone to {}'.format(node_id, api_params, zone_name))
				return zone_name

		raise DriverError(StatusCode.INTERNAL, 'Could not find node {} in any of the management servers. Topology: {}'.format(node_id, all_zones))

	@staticmethod
	def get_all_zones_from_topology():
		cluster_topology = Config.TOPOLOGY
		return cluster_topology.get('zones').keys()

	@staticmethod
	def get_topology_key():
		if not Config.TOPOLOGY:
			return consts.TopologyKey.ZONE

		return Config.TOPOLOGY.get('topologyKey', consts.TopologyKey.ZONE)

	@staticmethod
	def get_zone_from_topology(logger, topology_requirements):
		if Config.TOPOLOGY_TYPE == consts.TopologyType.SINGLE_ZONE_CLUSTER:
			return consts.SINGLE_CLUSTER_ZONE_NAME

		# provisioner sidecar container should have --strict-topology flag set
		# If volumeBindingMode is Immediate - all cluster topology will be received
		# If volumeBindingMode is WaitForFirstConsumer - Only the topology of the node to which the pod is scheduled will be given
		try:
			topology_key = TopologyUtils.get_topology_key()
			preferred_topologies = topology_requirements.get('preferred')
			if len(preferred_topologies) == 1:
				selected_zone = preferred_topologies[0]['segments'][topology_key]
			else:
				zones = map(lambda t: t['segments'][topology_key], preferred_topologies)
				selected_zone = ZoneSelectionManager.pick_zone(zones)
		except Exception as ex:
			raise ValueError('Failed to get zone from topology. Error: %s' % ex)

		if not selected_zone:
			raise DriverError(StatusCode.INVALID_ARGUMENT, 'Failed to get zone from topology')

		logger.debug('_get_zone_from_topology selected zone is {}'.format(selected_zone))
		return selected_zone

	@staticmethod
	def get_api_params_from_config():
		return {
			'managementServers': Config.MANAGEMENT_SERVERS,
			'managementProtocol': Config.MANAGEMENT_PROTOCOL,
			'user': Config.MANAGEMENT_USERNAME,
			'password': Config.MANAGEMENT_PASSWORD
		}

	@staticmethod
	def get_api_params(logger, zone):
		if Config.TOPOLOGY_TYPE == consts.TopologyType.SINGLE_ZONE_CLUSTER:
			return TopologyUtils.get_api_params_from_config()

		mgmt_info = TopologyUtils.get_management_info_from_zone(zone)

		if not mgmt_info:
			raise ValueError('Missing "management" key in Config.topology.zones.%s' % zone)

		managementServers = mgmt_info.get('servers')
		if not managementServers:
			raise ValueError('Missing "servers" key in Config.topology.zones.%s.management ' % zone)

		api_params = {
			'managementServers': managementServers
		}

		user = mgmt_info.get('user')
		password = mgmt_info.get('password')
		protocol = mgmt_info.get('protocol')

		if user:
			api_params['user'] = user

		if password:
			api_params['password'] = password

		if protocol:
			api_params['protocol'] = protocol

		return api_params

	@staticmethod
	def get_volume_api_for_zone(logger, zone=None):
		api_params = TopologyUtils.get_api_params(logger, zone)
		return NVMeshSDKHelper.get_volume_api(logger, api_params)

class ZoneSelectionManager(object):
	_zone_picker = None

	@staticmethod
	def get_instance():
		if not ZoneSelectionManager._zone_picker:
			ZoneSelectionManager._zone_picker = ZoneSelectionManager._initialize_instance()

		return ZoneSelectionManager._zone_picker

	@staticmethod
	def _initialize_instance():
		topology = Config.TOPOLOGY
		selection_policy = topology.get('zoneSelectionPolicy')
		if selection_policy == consts.ZoneSelectionPolicy.RANDOM:
			return RandomZonePicker()
		elif selection_policy == consts.ZoneSelectionPolicy.ROUND_ROBIN:
			return RoundRobinZonePicker()
		else:
			raise ValueError('Unknown zoneSelectionPolicy: %s ' % selection_policy)

	@staticmethod
	def pick_zone(zones):
		picker = ZoneSelectionManager.get_instance()
		return picker.pick_zone(zones)


class ZonePicker(object):
	def pick_zone(self, zones):
		raise ValueError('Not Implemented')


class RandomZonePicker(ZonePicker):
	def pick_zone(self, allowed_zones):
		zone = random.choice(allowed_zones)
		return zone


class RoundRobinZonePicker(ZonePicker):

	def __init__(self):
		self.zones_queue = Queue.Queue()
		self._build_queue()

	def _build_queue(self):
		topology_config = Config.TOPOLOGY
		for zone in topology_config.get('zones').keys():
			self.zones_queue.put(zone)

	def pick_zone(self, _unused):
		zone = self.zones_queue.get()
		self.zones_queue.put(zone)
		return zone


