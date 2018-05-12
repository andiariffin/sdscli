"""
SDSKit command line interface.
"""
from __future__ import absolute_import
from __future__ import print_function

import os, sys, importlib, json, yaml, traceback, argparse, logging
from importlib import import_module

import sdscli
from sdscli.func_utils import get_module, get_func
from sdscli.log_utils import logger


def get_adapter_func(sds_type, mod_name, func_name):
    """Import adapter function."""

    adapter_mod = 'sdscli.adapters.%s.%s' % (sds_type, mod_name)
    try: return get_func(adapter_mod, func_name)
    except ImportError:
        logger.error('Failed to import adapter module "%s" for SDS type "%s".' % (mod_name, sds_type))
        logger.error('Not implemented yet. Mahalo for trying. ;)')
        sys.exit(1)
    except AttributeError:
        logger.error('Failed to get function "%s" from adapter module "%s".' % (func_name, adapter_mod))
        logger.error('Not implemented yet. Mahalo for trying. ;)')
        sys.exit(1)


def configure(args):
    """Configure SDS config file."""

    logger.debug("got to configure(): %s" % args)
    sds_type = args.type
    logger.debug("sds_type: %s" % sds_type)
    func = get_adapter_func(sds_type, 'configure', 'configure') 
    logger.debug("func: %s" % func)
    func()


def update(args):
    """Update SDS components."""

    logger.debug("got to update(): %s" % args)
    sds_type = args.type
    logger.debug("sds_type: %s" % sds_type)
    func = get_adapter_func(sds_type, 'update', 'update') 
    logger.debug("func: %s" % func)
    func(args.component, args.debug, args.force)


def ship(args):
    """Ship verdi code/config bundle."""

    logger.debug("got to ship(): %s" % args)
    sds_type = args.type
    logger.debug("sds_type: %s" % sds_type)
    func = get_adapter_func(sds_type, 'update', 'ship') 
    logger.debug("func: %s" % func)
    func(args.encrypt, args.debug)


def start(args):
    """Start SDS components."""

    logger.debug("got to start(): %s" % args)
    sds_type = args.type
    logger.debug("sds_type: %s" % sds_type)
    func = get_adapter_func(sds_type, 'start', 'start') 
    logger.debug("func: %s" % func)
    func(args.component, args.debug, args.force)


def stop(args):
    """Stop SDS components."""

    logger.debug("got to stop(): %s" % args)
    sds_type = args.type
    logger.debug("sds_type: %s" % sds_type)
    func = get_adapter_func(sds_type, 'stop', 'stop') 
    logger.debug("func: %s" % func)
    func(args.component, args.debug, args.force)


def reset(args):
    """Reset SDS components."""

    logger.debug("got to reset(): %s" % args)
    sds_type = args.type
    logger.debug("sds_type: %s" % sds_type)
    func = get_adapter_func(sds_type, 'reset', 'reset') 
    logger.debug("func: %s" % func)
    func(args.component, args.debug, args.force)


def status(args):
    """SDS component status."""

    logger.debug("got to status(): %s" % args)
    sds_type = args.type
    logger.debug("sds_type: %s" % sds_type)
    func = get_adapter_func(sds_type, 'status', 'status') 
    logger.debug("func: %s" % func)
    func(args.component, args.debug)


def ci(args):
    """Continuous integration functions."""

    logger.debug("got to ci(): %s" % args)
    sds_type = args.type
    logger.debug("sds_type: %s" % sds_type)
    func = get_adapter_func(sds_type, 'ci', args.subparser)
    logger.debug("func: %s" % func)
    func(args)


def pkg(args):
    """SDS package managment functions."""

    logger.debug("got to pkg(): %s" % args)
    sds_type = args.type
    logger.debug("sds_type: %s" % sds_type)
    func = get_adapter_func(sds_type, 'pkg', 'import_pkg' if args.subparser == 'import' else args.subparser)
    logger.debug("func: %s" % func)
    func(args)


def cloud(args):
    """SDS cloud managment functions."""

    logger.debug("got to cloud(): %s" % args)
    sds_type = args.type
    logger.debug("sds_type: %s" % sds_type)
    func = get_adapter_func(sds_type, 'cloud', args.subparser)
    logger.debug("func: %s" % func)
    func(args)


def rules(args):
    """SDS user rules managment functions."""

    logger.debug("got to pkg(): %s" % args)
    sds_type = args.type
    logger.debug("sds_type: %s" % sds_type)
    func = get_adapter_func(sds_type, 'rules', 'import_rules' if args.subparser == 'import' else args.subparser)
    logger.debug("func: %s" % func)
    func(args)


def job_list(args):
    """Configure SDS config file."""

    logger.debug("got to job_list(): %s" % args)


def dispatch(args):
    """Dispatch to appropriate function."""

    # turn on debugging
    if args.debug: logger.setLevel(logging.DEBUG)

    logger.debug("args: %s" % args)

    if args.func:
        return args.func(args)
    else:
        logger.error("No func specified for args %s" % args)
        return 1


def main():
    """Process command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--debug', '-d', action='store_true', help="turn on debugging")
    subparsers = parser.add_subparsers(help='Functions')

    # parser for configure
    parser_configure = subparsers.add_parser('configure', help="configure SDS config file")
    parser_configure.add_argument('type', default='hysds', const='hysds', nargs='?',
                                  choices=['hysds', 'sdskit'])
    parser_configure.set_defaults(func=configure)

    # parser for update
    parser_update = subparsers.add_parser('update', help="update SDS components")
    parser_update.add_argument('--type', '-t', default='hysds', const='hysds', nargs='?',
                                  choices=['hysds', 'sdskit'])
    parser_update.add_argument('component', choices=['mozart', 'grq', 'metrics', 
                               'factotum', 'ci', 'verdi', 'all'])
    parser_update.add_argument('--force', '-f', action='store_true',
                             help="force update without user confirmation")
    parser_update.set_defaults(func=update)

    # parser for ship
    parser_ship = subparsers.add_parser('ship', help="ship verdi code/config bundle")
    parser_ship.add_argument('type', default='hysds', const='hysds', nargs='?',
                                  choices=['hysds', 'sdskit'])
    parser_ship.add_argument('--encrypt', '-e', action='store_true',
                             help="encrypt code/config bundle")
    parser_ship.set_defaults(func=ship)

    # parser for start
    parser_start = subparsers.add_parser('start', help="start SDS components")
    parser_start.add_argument('--type', '-t', default='hysds', const='hysds', nargs='?',
                              choices=['hysds', 'sdskit'])
    parser_start.add_argument('component', choices=['mozart', 'grq', 'metrics', 
                              'factotum', 'all'])
    parser_start.add_argument('--force', '-f', action='store_true',
                              help="force start without user confirmation")
    parser_start.set_defaults(func=start)

    # parser for stop
    parser_stop = subparsers.add_parser('stop', help="stop SDS components")
    parser_stop.add_argument('--type', '-t', default='hysds', const='hysds', nargs='?',
                             choices=['hysds', 'sdskit'])
    parser_stop.add_argument('component', choices=['mozart', 'grq', 'metrics', 
                             'factotum', 'all'])
    parser_stop.add_argument('--force', '-f', action='store_true',
                             help="force stop without user confirmation")
    parser_stop.set_defaults(func=stop)

    # parser for reset
    parser_reset = subparsers.add_parser('reset', help="reset SDS components")
    parser_reset.add_argument('--type', '-t', default='hysds', const='hysds', nargs='?',
                              choices=['hysds', 'sdskit'])
    parser_reset.add_argument('component', choices=['mozart', 'grq', 'metrics', 
                              'factotum', 'all'])
    parser_reset.add_argument('--force', '-f', action='store_true',
                             help="force reset without user confirmation")
    parser_reset.set_defaults(func=reset)

    # parser for status
    parser_status = subparsers.add_parser('status', help="status of SDS components")
    parser_status.add_argument('--type', '-t', default='hysds', const='hysds', nargs='?',
                               choices=['hysds', 'sdskit'])
    parser_status.add_argument('component', default='all', const='all', nargs='?',
                               choices=['mozart', 'grq', 'metrics', 'factotum', 'ci', 'verdi', 'all'])
    parser_status.set_defaults(func=status)

    # parser for ci
    parser_ci = subparsers.add_parser('ci', help="configure continuous integration for SDS cluster")
    parser_ci.add_argument('--type', '-t', default='hysds', const='hysds', nargs='?',
                               choices=['hysds', 'sdskit'])
    parser_ci_subparsers = parser_ci.add_subparsers(dest='subparser', help='Continuous integration functions')
    parser_ci_add_job = parser_ci_subparsers.add_parser('add_job', help="add Jenkins job")
    parser_ci_add_job.add_argument('repo', help='git repository url')
    parser_ci_add_job.add_argument('storage', choices=['s3', 's3s', 'azure', 'gs', 'dav', 'davs'],
                                   help='image storage type')
    parser_ci_add_job.add_argument('uid', help="image's ops UID")
    parser_ci_add_job.add_argument('gid', help="image's ops GID")
    parser_ci_add_job.add_argument('--branch', '-b', default=None,
                                   help="register git branch instead of release")
    parser_ci_add_job.add_argument('--token', '-k', action='store_true', help="use configured OAuth token")
    parser_ci.set_defaults(func=ci)

    # parser for pkg
    parser_pkg = subparsers.add_parser('pkg', help="SDS package management")
    parser_pkg.add_argument('--type', '-t', default='hysds', const='hysds', nargs='?',
                               choices=['hysds', 'sdskit'])
    parser_pkg_subparsers = parser_pkg.add_subparsers(dest='subparser', help='SDS package management functions')
    parser_pkg_ls = parser_pkg_subparsers.add_parser('ls', help="list SDS package ids")
    parser_pkg_export = parser_pkg_subparsers.add_parser('export', help="export SDS package")
    parser_pkg_export.add_argument('id', help='SDS package id to export')
    parser_pkg_export.add_argument('--outdir', '-o', default=".",
                                   help="root output directory of SDS package")
    parser_pkg_export.add_argument('--accounts', '-a', action='store_true', help="save allowed accounts")
    parser_pkg_import = parser_pkg_subparsers.add_parser('import', help="import SDS package")
    parser_pkg_import.add_argument('file', help='SDS package to import')
    parser_pkg_rm = parser_pkg_subparsers.add_parser('rm', help="remove SDS package")
    parser_pkg_rm.add_argument('id', help='SDS package id to remove')
    parser_pkg.set_defaults(func=pkg)

    # parser for cloud
    parser_cloud = subparsers.add_parser('cloud', help="SDS cloud management")
    parser_cloud.add_argument('--type', '-t', default='hysds', const='hysds', nargs='?',
                               choices=['hysds', 'sdskit'])
    parser_cloud_subparsers = parser_cloud.add_subparsers(dest='subparser', help='SDS cloud management functions')
    parser_cloud_ls = parser_cloud_subparsers.add_parser('ls', help="list configured cloud vendors")
    parser_cloud_asg = parser_cloud_subparsers.add_parser('asg', help="SDS cloud Autoscaling management")
    parser_cloud_asg.add_argument('--cloud', '-c', default='aws', const='aws', nargs='?',
                                  choices=['aws', 'azure', 'gcp'])
    parser_cloud_asg_subparsers = parser_cloud_asg.add_subparsers(dest='subparser2', help='SDS cloud Autoscaling management functions')
    parser_cloud_asg_ls = parser_cloud_asg_subparsers.add_parser('ls', help="list Autoscaling groups")
    parser_cloud_asg_create = parser_cloud_asg_subparsers.add_parser('create', help="create Autoscaling group")
    parser_cloud_storage = parser_cloud_subparsers.add_parser('storage', help="SDS cloud storage management")
    parser_cloud_storage.add_argument('--cloud', '-c', default='aws', const='aws', nargs='?',
                                  choices=['aws', 'azure', 'gcp'])
    parser_cloud_storage_subparsers = parser_cloud_storage.add_subparsers(dest='subparser2', help='SDS cloud storage management functions')
    parser_cloud_storage_ls = parser_cloud_storage_subparsers.add_parser('ls', help="list buckets")
    parser_cloud_storage_ship_style = parser_cloud_storage_subparsers.add_parser('ship_style', help="ship browse style to bucket")
    parser_cloud_storage_ship_style.add_argument('--bucket', '-b', default=None, help="bucket name")
    parser_cloud_storage_ship_style.add_argument('--encrypt', '-e', action='store_true',
                             help="encrypt")
    parser_cloud_storage_create_staging_area = parser_cloud_storage_subparsers.add_parser('create_staging_area',
                                                                                          help="provision staging area under bucket")
    parser_cloud_storage_create_staging_area.add_argument('--bucket', '-b', default=None, help="bucket name")
    parser_cloud_storage_create_staging_area.add_argument('--prefix', '-p', default="staging_area/", 
                                                          help="staging area prefix")
    parser_cloud_storage_create_staging_area.add_argument('--suffix', '-s', default=".met.json", 
                                                          help="staging area signal file suffix")
    parser_cloud.set_defaults(func=cloud)

    # parser for user rules
    parser_rules = subparsers.add_parser('rules', help="SDS user rules management")
    parser_rules.add_argument('--type', '-t', default='hysds', const='hysds', nargs='?',
                               choices=['hysds', 'sdskit'])
    parser_rules_subparsers = parser_rules.add_subparsers(dest='subparser', help='SDS user rules management functions')
    parser_rules_export = parser_rules_subparsers.add_parser('export', help="export user rules")
    parser_rules_export.add_argument('--outfile', '-o', default="user_rules.json",
                                   help="output JSON file for user rules")
    parser_rules_import = parser_rules_subparsers.add_parser('import', help="import user rules")
    parser_rules_import.add_argument('file', help='input JSON file for user rules import')
    parser_rules.set_defaults(func=rules)

    # parser for jobs
    parser_job = subparsers.add_parser('job', help="SDS job subcommand")
    job_subparsers = parser_job.add_subparsers(help="Job functions.")

    # parser for jobs listing
    parser_job_list = job_subparsers.add_parser('list', help="list SDS job counts")
    parser_job_list.add_argument("status", help="job status to list counts for")
    parser_job_list.set_defaults(func=job_list)

    # dispatch
    args = parser.parse_args()
    return dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
