# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Lint as: python3
"""Queries related to GCP Vertex AI Workbench Notebooks
"""

import enum
import logging
import re
from typing import Dict, Mapping

import googleapiclient.errors

from gcpdiag import caching, config, models, utils
from gcpdiag.queries import apis

HEALTH_STATE_KEY = 'healthState'
INSTANCES_KEY = 'instances'
NAME_KEY = 'name'


class InstanceHealthStateEnum(enum.Enum):
  """Vertex AI Workbench user-managed notebooks instance health states

  https://cloud.google.com/vertex-ai/docs/workbench/reference/rest/v1/projects.locations.instances/getInstanceHealth#healthstate
  """

  HEALTH_STATE_UNSPECIFIED = 'HEALTH_STATE_UNSPECIFIED'
  HEALTHY = 'HEALTHY'
  UNHEALTHY = 'UNHEALTHY'
  AGENT_NOT_INSTALLED = 'AGENT_NOT_INSTALLED'
  AGENT_NOT_RUNNING = 'AGENT_NOT_RUNNING'

  def __str__(self):
    return str(self.value)


class Instance(models.Resource):
  """Represent a Vertex AI Workbench user-managed notebook instance

  https://cloud.google.com/vertex-ai/docs/workbench/reference/rest/v1/projects.locations.instances#resource:-instance
  """

  _resource_data: dict

  def __init__(self, project_id, resource_data):
    super().__init__(project_id=project_id)
    self._resource_data = resource_data

  @property
  def full_path(self) -> str:
    """
    The 'name' of the instance is already in the full path form
    projects/{project}/locations/{location}/instances/{instance}.
    """
    return self._resource_data[NAME_KEY]

  @property
  def short_path(self) -> str:
    path = self.full_path
    path = re.sub(r'^projects/', '', path)
    path = re.sub(r'/locations/', '/', path)
    path = re.sub(r'/instances/', '/', path)
    return path

  @property
  def name(self) -> str:
    logging.info(self._resource_data)
    return self._resource_data[NAME_KEY]


@caching.cached_api_call
def get_instances(context: models.Context) -> Mapping[str, Instance]:
  instances: Dict[str, Instance] = {}
  if not apis.is_enabled(context.project_id, 'notebooks'):
    return instances
  logging.info(
      'fetching list of Vertex AI Workbench notebook instances in project %s',
      context.project_id)
  notebooks_api = apis.get_api('notebooks', 'v1', context.project_id)
  query = notebooks_api.projects().locations().instances().list(
      parent=f'projects/{context.project_id}/locations/-'
  )  #'-' (wildcard) all regions
  try:
    resp = query.execute(num_retries=config.API_RETRIES)
    if INSTANCES_KEY not in resp:
      return instances
    for resp_i in resp[INSTANCES_KEY]:
      # verify that we have some minimal data that we expect
      if NAME_KEY not in resp_i:
        raise RuntimeError(
            'missing instance name in projects.locations.instances.list response'
        )
      i = Instance(project_id=context.project_id, resource_data=resp_i)
      instances[i.full_path] = i
  except googleapiclient.errors.HttpError as err:
    raise utils.GcpApiError(err) from err
  return instances


@caching.cached_api_call
def get_instance_health_state(context: models.Context,
                              name: str) -> InstanceHealthStateEnum:
  instance_health_state = InstanceHealthStateEnum('HEALTH_STATE_UNSPECIFIED')
  if not apis.is_enabled(context.project_id, 'notebooks'):
    logging.error('Notebooks API is not enabled')
    return instance_health_state
  if not name:
    logging.error('Instance name not provided')
    return instance_health_state
  logging.info(
      'fetching Vertex AI user-managed notebook instance health state in project %s',
      context.project_id)
  notebooks_api = apis.get_api('notebooks', 'v1', context.project_id)
  query = notebooks_api.projects().locations().instances().getInstanceHealth(
      name=name)
  try:
    resp = query.execute(num_retries=config.API_RETRIES)
    if HEALTH_STATE_KEY not in resp:
      raise RuntimeError(
          'missing instance health state in projects.locations.instances:getInstanceHealth response'
      )
    instance_health_state = InstanceHealthStateEnum(resp[HEALTH_STATE_KEY])
    return instance_health_state
  except googleapiclient.errors.HttpError as err:
    raise utils.GcpApiError(err) from err
  return instance_health_state
