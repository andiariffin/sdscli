from __future__ import absolute_import
from __future__ import print_function

import os, re, json, boto3, hashlib, base64

from azure.storage import CloudStorageAccount
from azure.storage.blob import BlockBlobService

from pprint import pformat
from collections import OrderedDict
from operator import itemgetter
from fabric.api import execute, hide

from prompt_toolkit.shortcuts import prompt, print_tokens
from prompt_toolkit.styles import style_from_dict
from prompt_toolkit.validation import Validator, ValidationError
from pygments.token import Token

from sdscli.log_utils import logger
from sdscli.conf_utils import get_user_config_path, get_user_files_path, SettingsConf
from sdscli.os_utils import validate_dir
from sdscli.func_utils import get_func
from sdscli.prompt_utils import (YesNoValidator, SelectionValidator,
MultipleSelectionValidator, Ec2InstanceTypeValidator, PriceValidator, highlight,
print_component_header)
from .utils import *
from .asg import prompt_secgroup

from osaka.main import put


prompt_style = style_from_dict({
    Token.Alert: 'bg:#D8060C',
    Token.Username: '#D8060C',
    Token.Param: '#3CFF33',
})


@cloud_config_check
def ls(args, conf):
    """List all buckets."""

    container_list = []
    for c in get_buckets():
        container_list.append(c.name)
        print(c)

