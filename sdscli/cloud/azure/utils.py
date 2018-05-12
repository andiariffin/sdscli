from __future__ import absolute_import
from __future__ import print_function

import os, sys, azure.common
from azure.storage import CloudStorageAccount
from azure.storage.blob import BlockBlobService

from sdscli.conf_utils import SettingsConf
from sdscli.log_utils import logger


def is_configured():
    """Return if Azure account is configured."""
    conf = SettingsConf()

    if config.IS_EMULATED'
        account = CloudStorageAccount(is_emulated=True)
    else:
        account = CloudStorageAccount(account_name=conf.get('AZURE_STORAGE_ACCOUNT_NAME'), account_key=conf.get('AZURE_STORAGE_ACCOUNT_KEY'))
        
        # Create a Block Blob Service Object
        blockblob_service = account.create_block_blob_service()

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
def get_buckets(c=None, **kargs):
    """List all containers."""

    containers = blockblob_service.list_containers()
    return containers
