"""
SDS package management functions.
"""
from __future__ import unicode_literals
from __future__ import absolute_import
from __future__ import print_function

import os, json, yaml, requests, tarfile, shutil, traceback
from fabric.api import execute, hide

from prompt_toolkit.shortcuts import prompt, print_tokens
from prompt_toolkit.styles import style_from_dict
from prompt_toolkit.validation import Validator, ValidationError
from pygments.token import Token

from sdscli.log_utils import logger
from sdscli.conf_utils import get_user_files_path, SettingsConf
from sdscli.query_utils import run_query
from sdscli.os_utils import validate_dir, normpath

from osaka.main import get, put, rmall


def ls(args):
    """List HySDS packages."""

    # get user's SDS conf settings
    conf = SettingsConf()

    # query for containers
    es_url = "http://{}:9200".format(conf.get('MOZART_ES_PVT_IP'))
    hits = run_query(es_url, "containers", {
        "query": {
            "match_all": {}
        }
    })

    # list
    for hit in hits:
        logger.debug(json.dumps(hit, indent=2))
        print(hit['_id'])
    return


def export(args):
    """Export HySDS package."""

    # get user's SDS conf settings
    conf = SettingsConf()

    # container id
    cont_id = args.id

    # query for container
    mozart_es_url = "http://{}:9200".format(conf.get('MOZART_ES_PVT_IP'))
    grq_es_url = "http://{}:9200".format(conf.get('GRQ_ES_PVT_IP'))
    hits = run_query(mozart_es_url, "containers", {
        "query": {
            "term": { "_id": cont_id }
        }
    })
    if len(hits) == 0:
        logger.error("SDS package id {} not found.".format(cont_id))
        return 1
    cont_info = hits[0]['_source']
    logger.debug("cont_info: {}".format(json.dumps(cont_info, indent=2)))

    # set export directory
    outdir = normpath(args.outdir)
    export_name = "{}.sdspkg".format(cont_id)
    export_dir = os.path.join(outdir, export_name)
    logger.debug("export_dir: {}".format(export_dir))

    # if directory exists, stop
    if os.path.exists(export_dir):
        logger.error("SDS package export directory {} exists. Not continuing.".format(export_dir))
        return 1

    # create export directory
    validate_dir(export_dir)

    # download container
    get(cont_info['url'], export_dir)
    cont_info['url'] = os.path.basename(cont_info['url'])

    # query job specs
    job_specs = [i['_source'] for i in run_query(mozart_es_url, "job_specs", {
        "query": {
            "term": { "container.raw": cont_id }
        }
    })]
    logger.debug("job_specs: {}".format(json.dumps(job_specs, indent=2)))
    
    # backwards-compatible query
    if len(job_specs) == 0:
        logger.debug("Got no job_specs. Checking deprecated mappings:")
        job_specs = [i['_source'] for i in run_query(mozart_es_url, "job_specs", {
            "query": {
                "query_string": {
                    "query": "container:\"{}\"".format(cont_id)
                }
            }
        })]
        logger.debug("job_specs: {}".format(json.dumps(job_specs, indent=2)))

    # pull hysds_ios for each job_spec and download any dependency images
    hysds_ios = []
    dep_images = {}
    for job_spec in job_specs:
        # download dependency images
        for d in job_spec.get('dependency_images', []):
            if d['container_image_name'] in dep_images:
                d['container_image_url'] = dep_images[d['container_image_name']]
            else:
                # download container
                get(d['container_image_url'], export_dir)
                d['container_image_url'] = os.path.basename(d['container_image_url'])
                dep_images[d['container_image_name']] = d['container_image_url']


        # collect hysds_ios from mozart
        mozart_hysds_ios = [i['_source'] for i in run_query(mozart_es_url, "hysds_ios", {
            "query": {
                "term": { "job-specification.raw": job_spec['id'] }
            }
        })]
        logger.debug("Found {} hysds_ios on mozart for {}.".format(len(mozart_hysds_ios), job_spec['id']))

        # backwards-compatible query
        if len(mozart_hysds_ios) == 0:
            logger.debug("Got no hysds_ios from mozart. Checking deprecated mappings:")
            mozart_hysds_ios = [i['_source'] for i in run_query(mozart_es_url, "hysds_ios", {
                "query": {
                    "query_string": {
                        "query": "job-specification:\"{}\"".format(job_spec['id'])
                    }
                }
            })]
            logger.debug("Found {} hysds_ios on mozart for {}.".format(len(mozart_hysds_ios), job_spec['id']))
        hysds_ios.extend(mozart_hysds_ios)
        
        # collect hysds_ios from grq
        grq_hysds_ios = [i['_source'] for i in run_query(grq_es_url, "hysds_ios", {
            "query": {
                "term": { "job-specification.raw": job_spec['id'] }
            }
        })]
        logger.debug("Found {} hysds_ios on grq for {}.".format(len(grq_hysds_ios), job_spec['id']))

        # backwards-compatible query
        if len(mozart_hysds_ios) == 0:
            logger.debug("Got no hysds_ios from grq. Checking deprecated mappings:")
            grq_hysds_ios = [i['_source'] for i in run_query(grq_es_url, "hysds_ios", {
                "query": {
                    "query_string": {
                        "query": "job-specification:\"{}\"".format(job_spec['id'])
                    }
                }
            })]
            logger.debug("Found {} hysds_ios on grq for {}.".format(len(grq_hysds_ios), job_spec['id']))
        hysds_ios.extend(grq_hysds_ios)
    logger.debug("Found {} hysds_ios total.".format(len(hysds_ios)))

    # export allowed accounts
    if not args.accounts:
        for hysds_io in hysds_ios:
            if 'allowed_accounts' in hysds_io:
                del hysds_io['allowed_accounts']

    # dump manifest JSON
    manifest = {
        "containers" : cont_info,
        "job_specs": job_specs,
        "hysds_ios": hysds_ios,
    }
    manifest_file = os.path.join(export_dir, 'manifest.json')
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    # tar up hysds package
    tar_file = os.path.join(outdir, "{}.tar".format(export_name))
    with tarfile.open(tar_file, "w") as tar:
        tar.add(export_dir, arcname=os.path.relpath(export_dir, outdir))

    # remove package dir
    shutil.rmtree(export_dir)


def import_pkg(args):
    """Import HySDS package."""

    # get user's SDS conf settings
    conf = SettingsConf()

    # package tar file
    tar_file = normpath(args.file)
    if not os.path.isfile(tar_file):
        logger.error("HySDS package file {} doesn't exist.".format(tar_file))
        return 1
    logger.debug("tar_file: {}".format(tar_file))

    # extract
    outdir = os.path.dirname(tar_file)
    with tarfile.open(tar_file) as tar:
        export_name = tar.getnames()[0]
        tar.extractall(outdir)
    export_dir = os.path.join(outdir, export_name)
    logger.debug("export_dir: {}".format(export_dir))

    # detect export dir
    if not os.path.isdir(export_dir):
        logger.error("Cannot find HySDS package dir {}.".format(export_dir))
        return 1

    # read in manifest
    manifest_file = os.path.join(export_dir, 'manifest.json')
    with open(manifest_file) as f:
        manifest = json.load(f)
    logger.debug("manifest: {}".format(json.dumps(manifest, indent=2, sort_keys=True)))

    # get code bucket
    code_bucket = conf.get('CODE_CONTAINER')
    code_bucket_url = "azure://{}/{}".format(conf.get('AZURE_ENDPOINT'), code_bucket)
    az_cred = {"account_name": conf.get('AZURE_STORAGE_ACCOUNT_NAME'), "account_key": conf.get('AZURE_STORAGE_ACCOUNT_KEY')}
    logger.debug("code_bucket: {}".format(code_bucket))
    logger.debug("code_bucket_url: {}".format(code_bucket_url))

    # get ES endpoints
    mozart_es_url = "http://{}:9200".format(conf.get('MOZART_ES_PVT_IP'))
    grq_es_url = "http://{}:9200".format(conf.get('GRQ_ES_PVT_IP'))


    # upload container image and index container in ES
    cont_info = manifest['containers']
    cont_image = os.path.join(export_dir, cont_info['url'])
    cont_info['url'] = "{}/{}".format(code_bucket_url, cont_info['url'])
    put(cont_image, cont_info['url'], az_cred)
    r = requests.put("{}/containers/container/{}".format(mozart_es_url, cont_info['id']),
                     data=json.dumps(cont_info))
    r.raise_for_status()
    logger.debug(r.json())

    # index job_specs in ES and upload any dependency containers
    dep_images = {}
    for job_spec in manifest['job_specs']:
        # download dependency images
        for d in job_spec.get('dependency_images', []):
            if d['container_image_name'] in dep_images:
                d['container_image_url'] = dep_images[d['container_image_name']]
            else:
                # upload container
                dep_img = os.path.join(export_dir, d['container_image_url'])
                d['container_image_url'] = "{}/{}".format(code_bucket_url, d['container_image_url'])
                put(dep_img, d['container_image_url'])
                dep_images[d['container_image_name']] = d['container_image_url']
        r = requests.put("{}/job_specs/job_spec/{}".format(mozart_es_url, job_spec['id']),
                         data=json.dumps(job_spec))
        r.raise_for_status()
        logger.debug(r.json())

    # index hysds_ios in ES
    for hysds_io in manifest['hysds_ios']:
        component = hysds_io.get('component', 'tosca')
        es_url = mozart_es_url if component == 'mozart' else grq_es_url
        r = requests.put("{}/hysds_ios/hysds_io/{}".format(es_url, hysds_io['id']),
                         data=json.dumps(hysds_io))
        r.raise_for_status()
        logger.debug(r.json())

    # remove package dir
    shutil.rmtree(export_dir)


def rm(args):
    """Remove HySDS package."""

    # get user's SDS conf settings
    conf = SettingsConf()

    # container id
    cont_id = args.id

    # query for container
    mozart_es_url = "http://{}:9200".format(conf.get('MOZART_ES_PVT_IP'))
    grq_es_url = "http://{}:9200".format(conf.get('GRQ_ES_PVT_IP'))
    hits = run_query(mozart_es_url, "containers", {
        "query": {
            "term": { "_id": cont_id }
        }
    })
    if len(hits) == 0:
        logger.error("SDS package id {} not found.".format(cont_id))
        return 1
    cont_info = hits[0]['_source']
    logger.debug("cont_info: {}".format(json.dumps(cont_info, indent=2)))

    # delete container from code bucket and ES
    rmall(cont_info['url'])
    r = requests.delete("{}/containers/container/{}".format(mozart_es_url, cont_info['id']))
    r.raise_for_status()
    logger.debug(r.json())

    # query job specs
    job_specs = [i['_source'] for i in run_query(mozart_es_url, "job_specs", {
        "query": {
            "term": { "container.raw": cont_id }
        }
    })]
    logger.debug("job_specs: {}".format(json.dumps(job_specs, indent=2)))

    # delete job_specs and hysds_ios
    for job_spec in job_specs:
        # collect hysds_ios from mozart
        mozart_hysds_ios = [i['_source'] for i in run_query(mozart_es_url, "hysds_ios", {
            "query": {
                "term": { "job-specification.raw": job_spec['id'] }
            }
        })]
        logger.debug("Found {} hysds_ios on mozart for {}.".format(len(mozart_hysds_ios), job_spec['id']))
        for hysds_io in mozart_hysds_ios:
            r = requests.delete("{}/hysds_ios/hysds_io/{}".format(mozart_es_url, hysds_io['id']))
            r.raise_for_status()
            logger.debug(r.json())
        
        # collect hysds_ios from mozart
        grq_hysds_ios = [i['_source'] for i in run_query(grq_es_url, "hysds_ios", {
            "query": {
                "term": { "job-specification.raw": job_spec['id'] }
            }
        })]
        logger.debug("Found {} hysds_ios on grq for {}.".format(len(grq_hysds_ios), job_spec['id']))
        for hysds_io in grq_hysds_ios:
            r = requests.delete("{}/hysds_ios/hysds_io/{}".format(grq_es_url, hysds_io['id']))
            r.raise_for_status()
            logger.debug(r.json())

        # delete job_spec from ES
        r = requests.delete("{}/job_specs/job_spec/{}".format(mozart_es_url, job_spec['id']))
        r.raise_for_status()
        logger.debug(r.json())
