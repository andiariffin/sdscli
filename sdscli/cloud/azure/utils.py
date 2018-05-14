from __future__ import absolute_import
from __future__ import print_function

import os, sys, azure.common

# Azure-specific imports
from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.models import VirtualMachineScaleSet
from azure.storage.blob import BlockBlobService
from msrestazure.azure_exceptions import CloudError

from sdscli.conf_utils import SettingsConf
from sdscli.log_utils import logger


def open_connection():
    """ Connects to Microsoft Azure with the given credentials, creates an
    authentication token and uses that to get the ServicePrincipalCredentials which
    is needed to access any resources.
    Returns:
      A ServicePrincipalCredentials instance, that can be used to
      access or create any resources.
    """
    conf = SettingsConf()
    credentials = ServicePrincipalCredentials(client_id=conf.get('AZURE_APP_ID'), secret=conf.get('AZURE_APP_SECRET_KEY'), tenant=conf.get('AZURE_TENANT_ID'))
    return credentials


def is_configured():
    """ Contacts Azure with the given credentials to ensure that they are
    valid. Gets an access token and a Credentials instance in order to be
    able to access any resources.
    Args:
      parameters: A dict, containing all the parameters necessary to
        authenticate this user with Azure.
    Returns:
      True, if the credentials were valid.
      A list, of resource group names under the subscription.
    """
    conf = SettingsConf()
    credentials = open_connection()
    try:
        resource_client = ResourceManagementClient(credentials, conf.get('AZURE_SUBSCRIPTION_ID'))
        resource_groups = resource_client.resource_groups.list()
        rg_names = []
        for rg in resource_groups:
            rg_names.append(rg.name)
        return True, rg_names
    except CloudError:
        return False


def cloud_config_check(func):
    """Wrapper function to perform cloud config check."""

    def wrapper(*args, **kwargs):
        if is_configured():
            return func(*args, **kwargs)
        else:
            logger.error("Not configured for Azure.")
            sys.exit(1)
    return wrapper


@cloud_config_check
def get_vmss(c=None):
    """List all Virtual Machine Scale Set (VMSS)."""
    conf = SettingsConf()
    credentials = open_connection()
    compute_client = ComputeManagementClient(credentials, conf.get('AZURE_SUBSCRIPTION_ID'))
    vmss_list = compute_client.virtual_machine_scale_sets.list(conf.get('AZURE_RESOURCE_GROUP'))
    return vmss_list


@cloud_config_check
def get_buckets(c=None, **kargs):
    """List all containers."""

    containers = blockblob_service.list_containers()
    return containers
