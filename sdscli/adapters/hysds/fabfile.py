"""
Fabric file for HySDS.
"""
from __future__ import unicode_literals
from __future__ import absolute_import
from __future__ import print_function

import os, re, yaml, json, requests
from copy import deepcopy
from fabric.api import run, cd, put, sudo, prefix, env, settings
from fabric.contrib.files import upload_template, exists, append
from fabric.contrib.project import rsync_project

from sdscli.log_utils import logger
from sdscli.conf_utils import get_user_config_path, get_user_files_path
from sdscli.prompt_utils import highlight, blink


# ssh_opts and extra_opts for rsync and rsync_project
ssh_opts = "-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
extra_opts = "-k"

# repo regex
repo_re = re.compile(r'.+//.*?/(.*?)/(.*?)(?:\.git)?$')

# define private EC2 IP addresses for infrastructure hosts
context = {}
this_dir = os.path.dirname(os.path.abspath(__file__))
sds_cfg = get_user_config_path()
if not os.path.isfile(sds_cfg):
    raise RuntimeError("SDS configuration file doesn't exist. Run 'sds configure'.")
with open(sds_cfg) as f:
    context = yaml.load(f)

# define and build groups to reduce redundancy in defining roles

# mozart hosts
mozart_host = '%s' % context['MOZART_PVT_IP']
mozart_rabbit_host = '%s' % context['MOZART_RABBIT_PVT_IP']
mozart_redis_host = '%s' % context['MOZART_REDIS_PVT_IP']
mozart_es_host = '%s' % context['MOZART_ES_PVT_IP']

# metrics host
metrics_host = '%s' % context['METRICS_PVT_IP']
metrics_redis_host = '%s' % context['METRICS_REDIS_PVT_IP']
metrics_es_host = '%s' % context['METRICS_ES_PVT_IP']

# grq host
grq_host = '%s' % context['GRQ_PVT_IP']
grq_es_host = '%s' % context['GRQ_ES_PVT_IP']

# factotum host
factotum_host = '%s' % context['FACTOTUM_PVT_IP']

# continuous integration host
ci_host = '%s' % context['CI_PVT_IP']

# all verdi hosts
verdi_hosts = [
    '%s' % context['VERDI_PVT_IP'],
]

# define roles
env.roledefs = {
    'mozart': [ mozart_host ],
    'mozart-rabbit': [ mozart_rabbit_host ],
    'mozart-redis': [ mozart_redis_host ],
    'mozart-es': [ mozart_es_host ],
    'metrics': [ metrics_host ],
    'metrics-redis': [ metrics_redis_host ],
    'metrics-es': [ metrics_es_host ],
    'grq': [ grq_host ],
    'grq-es': [ grq_es_host ],
    'factotum': [ factotum_host ],
    'ci': [ ci_host ],
    'verdi': verdi_hosts,
}

# define key file
env.key_filename = context['KEY_FILENAME']
if not os.path.isfile(env.key_filename):
    raise RuntimeError("SSH key filename %s doesn't exist. " % env.key_filename +
                       "Run 'ssh-keygen -t rsa' or copy existing key.")

# abort on prompts (password, hosts, etc.)
env.abort_on_prompts = True

# do all tasks in parallel
env.parallel = True

# define ops home directory
ops_dir = context['OPS_HOME']

##########################
# general functions
##########################

def get_context(node_type=None):
    """Modify context based on host string."""

    ctx = deepcopy(context)

    # use public IP for build hosts not on infrastructure LAN
    #if env.host_string in (govcloud_build_verdi_host, jplcloud_build_verdi_host,
    #                       docker_build_verdi_host, ts_verdi_host, leaflet_host):
    #    for pvt_ip in ('MOZART_PVT_IP', 'METRICS_PVT_IP', 'GRQ_PVT_IP',
    #                   'FACTOTUM_PVT_IP', 'PUCCINI_PVT_IP', 'VERDI_PVT_IP',
    #                   'VERDI_ML_PVT_IP', 'GOVCLOUD_VERDI_PVT_IP',
    #                   'JPLCLOUD_VERDI_PVT_IP', 'DOCKER_VERDI_PVT_IP',
    #                   'VERDI_TS_PVT_IP'):
    #        ctx[pvt_ip] = ctx[pvt_ip.replace('_PVT_', '_PUB_')]

    if node_type == 'mozart':
        if ctx['MOZART_PVT_IP'] == ctx['MOZART_RABBIT_PVT_IP']:
            ctx['MOZART_RABBIT_PVT_IP'] = "127.0.0.1"
        if ctx['MOZART_PVT_IP'] == ctx['MOZART_REDIS_PVT_IP']:
            ctx['MOZART_REDIS_PVT_IP'] = "127.0.0.1"
        if ctx['MOZART_PVT_IP'] == ctx['MOZART_ES_PVT_IP']:
            ctx['MOZART_ES_PVT_IP'] = "127.0.0.1"

    if node_type == 'metrics':
        if ctx['METRICS_PVT_IP'] == ctx['METRICS_REDIS_PVT_IP']:
            ctx['METRICS_REDIS_PVT_IP'] = "127.0.0.1"
        if ctx['METRICS_PVT_IP'] == ctx['METRICS_ES_PVT_IP']:
            ctx['METRICS_ES_PVT_IP'] = "127.0.0.1"

    if node_type == 'grq':
        if ctx['GRQ_PVT_IP'] == ctx['GRQ_ES_PVT_IP']:
            ctx['GRQ_ES_PVT_IP'] = "127.0.0.1"

    # set hostname
    ctx['HOST_STRING'] = env.host_string

    # split LDAP groups
    ctx['LDAP_GROUPS'] = [i.strip() for i in ctx['LDAP_GROUPS'].split(',')]

    return ctx


def resolve_files_dir(fname, files_dir):
    """Resolve file or template from user SDS files or default location."""

    user_path = get_user_files_path()
    return user_path if os.path.exists(os.path.join(user_path, fname)) else files_dir


def resolve_role():
    """Resolve role and hysds directory."""

    for role in env.effective_roles:
        if env.host_string in env.roledefs[role]:
            if '@' in env.host_string:
                hostname = env.host_string.split('@')[1]
            else: hostname = env.host_string
            break
    if role in ('factotum', 'ci'): hysds_dir = "verdi"
    elif role == 'grq': hysds_dir = "sciflo"
    else: hysds_dir = role
    return role, hysds_dir, hostname


def host_type():
    run('uname -s')


def fqdn():
    run('hostname --fqdn')


def yum_update():
    sudo('yum -y -q update')


def yum_install(package):
    sudo('yum -y install %s' % package)


def yum_remove(package):
    sudo('yum -y remove %s' % package)


def ps_x():
    run('ps x')


def df_hv():
    run('df -hv')


def echo(s):
    run('echo "%s"' % s)


def mpstat():
    sudo('mpstat -P ALL 5 1')


def copy(src, dest):
    put(src, dest)


def ln_sf(src,dest):
    if exists(dest): run('rm -rf %s' % dest)
    with cd(os.path.dirname(dest)):
        run('ln -sf %s %s' % (src, os.path.basename(dest)))


def cp_rp(src, dest):
    run('cp -rp %s %s' % (src, dest))


def cp_rp_exists(src, dest):
    if exists(src): run('cp -rp %s %s' % (src, dest))


def rm_rf(path):
    run('rm -rf %s' % path)


def sudo_rm_rf(path):
    run('sudo rm -rf %s' % path)


def send_template(tmpl, dest, tmpl_dir=None, node_type=None):
    if tmpl_dir is None: tmpl_dir = get_user_files_path()
    else: tmpl_dir = os.path.expanduser(tmpl_dir)
    upload_template(tmpl, dest, use_jinja=True, context=get_context(node_type),
                    template_dir=tmpl_dir)


def send_template_user_override(tmpl, dest, tmpl_dir=None, node_type=None):
    if tmpl_dir is None: tmpl_dir = get_user_files_path()
    else: tmpl_dir = os.path.expanduser(tmpl_dir)
    upload_template(tmpl, dest, use_jinja=True, context=get_context(node_type),
                    template_dir=resolve_files_dir(tmpl, tmpl_dir))


def set_spyddder_settings():
    upload_template('settings.json.tmpl', '~/verdi/ops/spyddder-man/settings.json', use_jinja=True,
                    context=get_context(), template_dir=os.path.join(ops_dir, 'mozart/ops/spyddder-man'))


def rsync_code(node_type, dir_path=None):
    if dir_path is None: dir_path = node_type
    rm_rf('%s/ops/osaka' % dir_path)
    rsync_project('%s/ops/' % dir_path, os.path.join(ops_dir, 'mozart/ops/osaka'),
                  extra_opts=extra_opts, ssh_opts=ssh_opts)
    rm_rf('%s/ops/hysds_commons' % dir_path)
    rsync_project('%s/ops/' % dir_path, os.path.join(ops_dir, 'mozart/ops/hysds_commons'),
                  extra_opts=extra_opts, ssh_opts=ssh_opts)
    rm_rf('%s/ops/hysds' % dir_path)
    rsync_project('%s/ops/' % dir_path, os.path.join(ops_dir, 'mozart/ops/hysds'),
                  extra_opts=extra_opts, ssh_opts=ssh_opts)
    rm_rf('%s/ops/prov_es' % dir_path)
    rsync_project('%s/ops/' % dir_path, os.path.join(ops_dir, 'mozart/ops/prov_es'),
                  extra_opts=extra_opts, ssh_opts=ssh_opts)
    rm_rf('%s/ops/sciflo' % dir_path)
    rsync_project('%s/ops/' % dir_path, os.path.join(ops_dir, 'mozart/ops/sciflo'),
                  extra_opts=extra_opts, ssh_opts=ssh_opts)
    rm_rf('%s/ops/container-builder' % dir_path)
    rsync_project('%s/ops/' % dir_path, os.path.join(ops_dir, 'mozart/ops/container-builder'),
                  extra_opts=extra_opts, ssh_opts=ssh_opts)
    rm_rf('%s/ops/lightweight-jobs' % dir_path)
    rsync_project('%s/ops/' % dir_path, os.path.join(ops_dir, 'mozart/ops/lightweight-jobs'),
                  extra_opts=extra_opts, ssh_opts=ssh_opts)
    rm_rf('%s/ops/hysds-dockerfiles' % dir_path)
    rsync_project('%s/ops/' % dir_path, os.path.join(ops_dir, 'mozart/ops/hysds-dockerfiles'),
                  extra_opts=extra_opts, ssh_opts=ssh_opts)
    if node_type in ('mozart'):
        rm_rf('%s/ops/mozart' % dir_path)
        rsync_project('%s/ops/' % dir_path, os.path.join(ops_dir, 'mozart/ops/mozart'),
                      extra_opts=extra_opts, ssh_opts=ssh_opts)
        rm_rf('%s/ops/figaro' % dir_path)
        rsync_project('%s/ops/' % dir_path, os.path.join(ops_dir, 'mozart/ops/figaro'),
                      extra_opts=extra_opts, ssh_opts=ssh_opts)
    if node_type == 'verdi':
        rm_rf('%s/ops/spyddder-man' % dir_path)
        rsync_project('%s/ops/' % dir_path, os.path.join(ops_dir, 'mozart/ops/spyddder-man'),
                      extra_opts=extra_opts, ssh_opts=ssh_opts)
    if node_type == 'factotum':
        rm_rf('%s/ops/spyddder-man' % dir_path)
        rsync_project('%s/ops/' % dir_path, os.path.join(ops_dir, 'mozart/ops/spyddder-man'),
                      extra_opts=extra_opts, ssh_opts=ssh_opts)
    if node_type == 'grq':
        rm_rf('%s/ops/grq2' % dir_path)
        rsync_project('%s/ops/' % dir_path, os.path.join(ops_dir, 'mozart/ops/grq2'),
                      extra_opts=extra_opts, ssh_opts=ssh_opts)
        rm_rf('%s/ops/tosca' % dir_path)
        rsync_project('%s/ops/' % dir_path, os.path.join(ops_dir, 'mozart/ops/tosca'),
                      extra_opts=extra_opts, ssh_opts=ssh_opts)


def svn_co(path, svn_url):
    if not exists(path):
        with cd(os.path.dirname(path)):
            run('svn co --non-interactive --trust-server-cert %s' % svn_url)


def svn_rev(rev, path):
    run('svn up -r %s %s' % (rev, path))


def grep(grep_str, dir_path):
    try: run('grep -r %s %s' % (grep_str, dir_path))
    except: pass


def chmod(perms, path):
    run('chmod -R %s %s' % (perms, path))


def reboot():
    sudo('reboot')


def mkdir(d, o, g):
    #sudo('mkdir -p %s' % d)
    #sudo('chown -R %s:%s %s' % (o, g, d))
    run("mkdir -p %s" % d)

def untar(tarfile, chdir):
    with cd(chdir):
        run('tar xvfj %s' % tarfile)


def untar_gz(cwd, tar_file):
    with cd(cwd):
        run('tar xvfz %s' % tar_file)


def untar_bz(cwd, tar_file):
    with cd(cwd):
        run('tar xvfj %s' % tar_file)


def mv(src, dest):
    sudo('mv -f %s %s' % (src, dest))


def rsync(src, dest):
    rsync_project(dest, src, extra_opts=extra_opts, ssh_opts=ssh_opts)


def remove_docker_images():
    run('docker rmi -f $(docker images -q)')


def remove_running_containers():
    run('docker rm -f $(docker ps -aq)')


def remove_docker_volumes():
    run('docker volume rm $(docker volume ls -q)')


def list_docker_images():
    run('docker images')


def stop_docker_containers():
    run('docker stop $(docker ps -aq)')


def status():
    role, hysds_dir, hostname = resolve_role()
    if exists('%s/run/supervisor.sock' % hysds_dir):
        with prefix('source %s/bin/activate' % hysds_dir):
            run('supervisorctl status')
    else:
        print(blink(highlight("Supervisord is not running on %s." % role, 'red')))


def ensure_venv(hysds_dir):
    act_file = "~/%s/bin/activate" % hysds_dir
    if not exists(act_file):
        run("virtualenv --system-site-packages %s" % hysds_dir)
        with prefix('source %s/bin/activate' % hysds_dir):
            run('pip install -U pip')
            run('pip install -U setuptools')
            run('pip install --ignore-installed supervisor')
            mkdir('%s/etc' % hysds_dir, context['OPS_USER'], context['OPS_USER'])
            mkdir('%s/log' % hysds_dir, context['OPS_USER'], context['OPS_USER'])
            mkdir('%s/run' % hysds_dir, context['OPS_USER'], context['OPS_USER'])
    append('.bash_profile', "source $HOME/{}/bin/activate".format(hysds_dir), escape=True)
    append('.bash_profile', "export FACTER_ipaddress=$(ifconfig $(route | awk '/default/{print $NF}') | grep 'inet ' | sed 's/addr://' | awk '{print $2}')", escape=True)


def install_pkg_es_templates():
    role, hysds_dir, hostname = resolve_role()
    if role not in ('grq', 'mozart'):
        raise RuntimeError("Invalid fabric function for %s." % role)
    with prefix('source %s/bin/activate' % hysds_dir):
        run('%s/ops/hysds_commons/scripts/install_es_template.sh %s' % (hysds_dir, role))


##########################
# grq functions
##########################

def grqd_start(force=False):
    mkdir('sciflo/run', context['OPS_USER'], context['OPS_USER'])
    if not exists('sciflo/run/supervisord.pid') or force:
        with prefix('source sciflo/bin/activate'):
            run('supervisord')


def grqd_clean_start():
    run('rm -rf %s/sciflo/log/*' % ops_dir)
    #with prefix('source %s/sciflo/bin/activate' % ops_dir):
    #    with cd(os.path.join(ops_dir, 'sciflo/ops/grq2/scripts')):
    #        run('./reset_dumby_indices.sh')
    grqd_start(True)


def grqd_stop():
    if exists('sciflo/run/supervisor.sock'):
        with prefix('source sciflo/bin/activate'):
            run('supervisorctl shutdown')


def install_es_template():
    with prefix('source sciflo/bin/activate'):
        run('sciflo/ops/grq2/scripts/install_es_template.sh')


def clean_hysds_ios():
    with prefix('source sciflo/bin/activate'):
        run('sciflo/ops/tosca/scripts/clean_hysds_ios_indexes.sh http://localhost:9200')


##########################
# mozart functions
##########################

def mozartd_start(force=False):
    if not exists('mozart/run/supervisord.pid') or force:
        with prefix('source mozart/bin/activate'):
            run('supervisord')


def mozartd_clean_start():
    run('rm -rf %s/mozart/log/*' % ops_dir)
    mozartd_start(True)


def mozartd_stop():
    if exists('mozart/run/supervisor.sock'):
        with prefix('source mozart/bin/activate'):
            run('supervisorctl shutdown')


def redis_flush():
    run('redis-cli flushall')


def mozart_redis_flush():
    ctx = get_context()
    run('redis-cli -h {MOZART_REDIS_PVT_IP} flushall'.format(**ctx))


def rabbitmq_queues_flush():
    ctx = get_context()
    url = 'http://%s:15672/api/queues' % ctx['MOZART_RABBIT_PVT_IP']
    r = requests.get('%s?columns=name' % url, auth=(ctx['MOZART_RABBIT_USER'], 
                     ctx['MOZART_RABBIT_PASSWORD']))
    r.raise_for_status()
    res = r.json()
    for i in res:
        r = requests.delete('%s/%%2f/%s' % (url, i['name']),
                            auth=(ctx['MOZART_RABBIT_USER'], ctx['MOZART_RABBIT_PASSWORD']))
        r.raise_for_status()
        logger.debug("Deleted queue %s." % i['name'])


def mozart_es_flush():
    ctx = get_context()
    run('curl -XDELETE http://{MOZART_ES_PVT_IP}:9200/_template/*_status'.format(**ctx))
    run('~/mozart/ops/hysds/scripts/clean_job_status_indexes.sh http://{MOZART_ES_PVT_IP}:9200'.format(**ctx))
    run('~/mozart/ops/hysds/scripts/clean_task_status_indexes.sh http://{MOZART_ES_PVT_IP}:9200'.format(**ctx))
    run('~/mozart/ops/hysds/scripts/clean_worker_status_indexes.sh http://{MOZART_ES_PVT_IP}:9200'.format(**ctx))
    run('~/mozart/ops/hysds/scripts/clean_event_status_indexes.sh http://{MOZART_ES_PVT_IP}:9200'.format(**ctx))
    #run('~/mozart/ops/hysds/scripts/clean_job_spec_container_indexes.sh http://{MOZART_ES_PVT_IP}:9200'.format(**ctx))


##########################
# metrics functions
##########################

def metricsd_start(force=False):
    if not exists('metrics/run/supervisord.pid') or force:
        with prefix('source metrics/bin/activate'):
            run('supervisord')


def metricsd_clean_start():
    run('rm -rf /home/ops/metrics/log/*')
    metricsd_start(True)


def metricsd_stop():
    if exists('metrics/run/supervisor.sock'):
        with prefix('source metrics/bin/activate'):
            run('supervisorctl shutdown')


##########################


##########################
# verdi functions
##########################

def kill_hung():
    try: run('ps x | grep [j]ob_worker | awk \'{print $1}\' | xargs kill -TERM', quiet=True)
    except: pass
    try: run('ps x | grep [s]flExec | awk \'{print $1}\' | xargs kill -TERM', quiet=True)
    except: pass
    try: run('ps x | grep [s]flExec | awk \'{print $1}\' | xargs kill -KILL', quiet=True)
    except: pass
    ps_x()


def verdid_start(force=False):
    if not exists('verdi/run/supervisord.pid') or force:
        with prefix('source verdi/bin/activate'):
            run('supervisord')


def verdid_clean_start():
    run('rm -rf /data/work/scifloWork-ops/* /data/work/jobs/* %s/verdi/log/*' % ops_dir)
    verdid_start(True)


def verdid_stop():
    if exists('verdi/run/supervisor.sock'):
        with prefix('source verdi/bin/activate'):
            run('supervisorctl shutdown')


def supervisorctl_up():
    with prefix('source verdi/bin/activate'):
        run('supervisorctl reread')
        run('supervisorctl update')


def supervisorctl_status():
    with prefix('source verdi/bin/activate'):
        run('supervisorctl status')


def pip_install(pkg, node_type='verdi'):
    with prefix('source ~/%s/bin/activate' % node_type):
        run('pip install %s' % pkg)


def pip_upgrade(pkg, node_type='verdi'):
    with prefix('source ~/%s/bin/activate' % node_type):
        run('pip install -U %s' % pkg)


def pip_uninstall(pkg, node_type='verdi'):
    with prefix('source ~/%s/bin/activate' % node_type):
        run('pip uninstall -y %s' % pkg)


def pip_install_with_req(node_type, dest):
    with prefix('source ~/%s/bin/activate' % node_type):
        with cd(dest):
            run('pip install --process-dependency-links -e .')


def python_setup_develop(node_type, dest):
    with prefix('source ~/%s/bin/activate' % node_type):
        with cd(dest):
            run('python setup.py develop')


##########################
# ci functions
##########################

def add_ci_job(repo, proto, uid=1001, gid=1001, branch=None, release=False):
    with settings(sudo_user=context["JENKINS_USER"]):
        match = repo_re.search(repo)
        if not match:
            raise RuntimeError("Failed to parse repo owner and name: %s" % repo)   
        owner, name = match.groups()
        if branch is None:
            job_name = "container-builder_%s_%s" % (owner, name)
            config_tmpl = 'config.xml'
        else:
            job_name = "container-builder_%s_%s_%s" % (owner, name, branch)
            config_tmpl = 'config-branch.xml'
        ctx = get_context()
        ctx['PROJECT_URL'] = repo
        ctx['BRANCH'] = branch
        ctx['UID'] = uid
        ctx['GID'] = gid
        job_dir = '%s/jobs/%s' % (ctx['JENKINS_DIR'], job_name)
        dest_file = '%s/config.xml' % job_dir
        mkdir(job_dir, None, None)
        chmod('777', job_dir)
        if release: ctx['BRANCH_SPEC'] = "origin/tags/release-*"
        else: ctx['BRANCH_SPEC'] = "**"
        if proto in ('s3', 's3s'):
            ctx['STORAGE_URL'] = "%s://%s/%s/" % (proto, ctx['S3_ENDPOINT'], ctx['CODE_BUCKET'])
        elif proto == 'gs':
            ctx['STORAGE_URL'] = "%s://%s/%s/" % (proto, ctx['GS_ENDPOINT'], ctx['CODE_BUCKET'])
        elif proto in ('dav', 'davs'):
            ctx['STORAGE_URL'] = "%s://%s:%s@%s/repository/products/containers/" % \
                                 (proto, ctx['DAV_USER'], ctx['DAV_PASSWORD'], ctx['DAV_SERVER'])
        elif proto in ('azure'):
            ctx['STORAGE_URL'] = "%s://%s/%s/" % (proto, ctx['AZURE_ENDPOINT'], ctx['CODE_CONTAINER'])
        else:
            raise RuntimeError("Unrecognized storage type for containers: %s" % proto)
        upload_template(config_tmpl, "tmp-jenkins-upload", use_jinja=True, context=ctx,
                        template_dir=get_user_files_path())
        cp_rp("tmp-jenkins-upload", dest_file)
        run("rm tmp-jenkins-upload")


def add_ci_job_release(repo, proto, uid=1001, gid=1001):
    add_ci_job(repo, proto, uid, gid, release=True)


def reload_configuration():
    ctx = get_context()
    juser=ctx.get("JENKINS_API_USER","").strip()
    jkey=ctx.get("JENKINS_API_KEY","").strip()
    if juser == "" or jkey == "":
        raise RuntimeError("An API user/key is needed for Jenkins.  Reload manually or specify one.")
    with prefix('source verdi/bin/activate'):
        run('java -jar %s/war/WEB-INF/jenkins-cli.jar -s http://localhost:8080 -http -auth %s:%s reload-configuration' % \
            (ctx['JENKINS_DIR'], juser,jkey))


##########################
# logstash functions
##########################

def send_shipper_conf(node_type, log_dir, cluster_jobs, redis_ip_job_status,
                      cluster_metrics, redis_ip_metrics):
    role, hysds_dir, hostname = resolve_role()

    ctx = get_context(node_type)
    if node_type == 'mozart':
        ctx.update({'cluster_jobs': cluster_jobs, 'cluster_metrics': cluster_metrics })
        upload_template('indexer.conf.mozart', '~/mozart/etc/indexer.conf', use_jinja=True, context=ctx,
                        template_dir=os.path.join(ops_dir, 'mozart/ops/hysds/configs/logstash'))
        upload_template('job_status.template', '~/mozart/etc/job_status.template', use_jinja=True,
                        template_dir=os.path.join(ops_dir, 'mozart/ops/hysds/configs/logstash'))
        upload_template('worker_status.template', '~/mozart/etc/worker_status.template', use_jinja=True,
                        template_dir=os.path.join(ops_dir, 'mozart/ops/hysds/configs/logstash'))
        upload_template('task_status.template', '~/mozart/etc/task_status.template', use_jinja=True,
                        template_dir=os.path.join(ops_dir, 'mozart/ops/hysds/configs/logstash'))
        upload_template('event_status.template', '~/mozart/etc/event_status.template', use_jinja=True,
                        template_dir=os.path.join(ops_dir, 'mozart/ops/hysds/configs/logstash'))
    elif node_type == 'metrics':
        ctx.update({'cluster_jobs': cluster_jobs, 'cluster_metrics': cluster_metrics })
        upload_template('indexer.conf.metrics', '~/metrics/etc/indexer.conf', use_jinja=True, context=ctx,
                        template_dir=os.path.join(ops_dir, 'mozart/ops/hysds/configs/logstash'))
        upload_template('job_status.template', '~/metrics/etc/job_status.template', use_jinja=True,
                        template_dir=os.path.join(ops_dir, 'mozart/ops/hysds/configs/logstash'))
        upload_template('worker_status.template', '~/metrics/etc/worker_status.template', use_jinja=True,
                        template_dir=os.path.join(ops_dir, 'mozart/ops/hysds/configs/logstash'))
        upload_template('task_status.template', '~/metrics/etc/task_status.template', use_jinja=True,
                        template_dir=os.path.join(ops_dir, 'mozart/ops/hysds/configs/logstash'))
        upload_template('event_status.template', '~/metrics/etc/event_status.template', use_jinja=True,
                        template_dir=os.path.join(ops_dir, 'mozart/ops/hysds/configs/logstash'))
    else: raise RuntimeError("Unknown node type: %s" % node_type) 


def send_celeryconf(node_type):
    template_dir = os.path.join(ops_dir, 'mozart/ops/hysds/configs/celery')
    if node_type == 'mozart': base_dir = "mozart"
    elif node_type == 'metrics': base_dir = "metrics"
    elif node_type in ('verdi', 'verdi-asg'): base_dir = "verdi"
    elif node_type == 'grq': base_dir = "sciflo"
    else: raise RuntimeError("Unknown node type: %s" % node_type)
    ctx = get_context(node_type)
    dest_file = '~/%s/ops/hysds/celeryconfig.py' % base_dir
    upload_template('celeryconfig.py.tmpl', dest_file, use_jinja=True, context=ctx,
                    template_dir=template_dir)


def send_mozartconf():
    dest_file = '~/mozart/ops/mozart/settings.cfg'
    upload_template('settings.cfg.tmpl', dest_file, use_jinja=True, context=get_context('mozart'),
                    template_dir=os.path.join(ops_dir, 'mozart/ops/mozart/settings'))
    with prefix('source ~/mozart/bin/activate'):
        with cd('~/mozart/ops/mozart'):
            mkdir('~/mozart/ops/mozart/data', context['OPS_USER'], context['OPS_USER'])
            run('./db_create.py')


def send_figaroconf():
    dest_file = '~/mozart/ops/figaro/settings.cfg'
    #upload_template('settings.cfg.tmpl', dest_file, use_jinja=True, context=get_context('mozart'),
    #                template_dir=os.path.join(ops_dir, 'mozart/ops/figaro/settings'))
    upload_template('figaro_settings.cfg.tmpl', dest_file, use_jinja=True, context=get_context('mozart'),
                    template_dir=get_user_files_path())
    with prefix('source ~/mozart/bin/activate'):
        with cd('~/mozart/ops/figaro'):
            mkdir('~/mozart/ops/figaro/data', context['OPS_USER'], context['OPS_USER'])
            run('./db_create.py')


def send_grq2conf():
    dest_file = '~/sciflo/ops/grq2/settings.cfg'
    upload_template('settings.cfg.tmpl', dest_file, use_jinja=True, context=get_context('grq'),
                    template_dir=os.path.join(ops_dir, 'mozart/ops/grq2/config'))


def send_toscaconf(send_file='settings.cfg.tmpl', template_dir=get_user_files_path()):
    tmpl_dir = os.path.expanduser(template_dir)
    dest_file = '~/sciflo/ops/tosca/settings.cfg'
    upload_template(send_file, dest_file, use_jinja=True, context=get_context('grq'),
                    template_dir=tmpl_dir)
    with prefix('source ~/sciflo/bin/activate'):
        with cd('~/sciflo/ops/tosca'):
            run('./db_create.py')


def create_user_rules_index():
    with prefix('source ~/mozart/bin/activate'):
        with cd('~/mozart/ops/mozart/scripts'):
            run('./create_user_rules_index.py')



##########################
# self-signed SSL certs
##########################

def ensure_ssl(node_type):
    ctx = get_context(node_type)
    if node_type == "grq": commonName = ctx['GRQ_FQDN']
    elif node_type == "mozart": commonName = ctx['MOZART_FQDN']
    else: raise RuntimeError("Unknown node type: %s" % node_type) 
    prompts = {
        'Enter pass phrase for server.key:': 'hysds',
        'Enter pass phrase for server.key.org:': 'hysds',
        'Verifying - Enter pass phrase for server.key:': 'hysds',
    }
    if not exists('ssl/server.key') or not exists('ssl/server.pem'):
        mkdir('ssl', context['OPS_USER'], context['OPS_USER'])
        upload_template('ssl_server.cnf', 'ssl/server.cnf', use_jinja=True,
                        context={ 'commonName': commonName },
                        template_dir=get_user_files_path())
        with cd('ssl'):
            with settings(prompts=prompts):
                run('openssl genrsa -des3 -out server.key 1024')
                run('OPENSSL_CONF=server.cnf openssl req -new -key server.key -out server.csr')
                run('cp server.key server.key.org')
                run('openssl rsa -in server.key.org -out server.key')
                run('chmod 600 server.key*')
                run('openssl x509 -req -days 99999 -in server.csr -signkey server.key -out server.pem')


##########################
# ship code
##########################

def ship_code(cwd, tar_file, encrypt=False):
    ctx = get_context()
    with cd(cwd):
        run('tar --exclude-vcs -cvjf %s *' % tar_file)
    if encrypt is False:
        run('aws s3 cp %s s3://%s/' % (tar_file, ctx['CODE_BUCKET']))
        # Azure Cli support to Azure Blob Storage
        # Azure Blob storage is encrypted with SSE by default - additional settings can be configured with own key on Azure Key Vault
        run('az storage blob upload -f %s -c %s -n %s --connection-string %s' % (tar_file, ctx['CODE_CONTAINER'], ctx['CODE_BLOB'], ctx['AZ_STORAGE_ACCOUNT']))
    else:
        run('aws s3 cp --sse %s s3://%s/' % (tar_file, ctx['CODE_BUCKET']))
        # Azure Cli support to Azure Blob Storage
        # Azure Blob storage is encrypted with SSE by default - additional settings can be configured with own key on Azure Key Vault
        run('az storage blob upload -f %s -c %s -n %s --connection-string %s' % (tar_file, ctx['CODE_CONTAINER'], ctx['CODE_BLOB'], ctx['AZ_STORAGE_ACCOUNT']))


##########################
# ship creds
##########################

def send_awscreds():
    ctx = get_context()
    if exists('.aws'): run('rm -rf .aws')
    mkdir('.aws', context['OPS_USER'], context['OPS_USER'])
    run('chmod 700 .aws')
    upload_template('aws_config', '.aws/config', use_jinja=True, context=ctx,
                    template_dir=get_user_files_path())
    upload_template('aws_credentials', '.aws/credentials', use_jinja=True, context=ctx,
                    template_dir=get_user_files_path())
    run('chmod 600 .aws/*')
    if exists('.boto'): run('rm -rf .boto')
    upload_template('boto', '.boto', use_jinja=True, context=ctx,
                    template_dir=get_user_files_path())
    run('chmod 600 .boto')
    if exists('.s3cfg'): run('rm -rf .s3cfg')
    upload_template('s3cfg', '.s3cfg', use_jinja=True, context=ctx,
                    template_dir=get_user_files_path())
    run('chmod 600 .s3cfg')


##########################
# ship verdi code bundle
##########################

def send_project_config(project):
    ctx = get_context()
    ctx.update({'project': project})
    upload_template('install.sh', '~/verdi/ops/install.sh', use_jinja=True, context=ctx,
                    template_dir=get_user_files_path())
    upload_template('datasets.json.tmpl.asg', '~/verdi/etc/datasets.json',
                    use_jinja=True, context=ctx, template_dir=get_user_files_path())
    upload_template('supervisord.conf.tmpl', '~/verdi/etc/supervisord.conf.tmpl',
                    use_jinja=True, context=ctx, template_dir=get_user_files_path())


##########################
# ship s3-bucket style
##########################

def ship_style(bucket=None, encrypt=False):
    ctx = get_context()
    if bucket is None: bucket = ctx['DATASET_BUCKET']
    repo_dir = os.path.join(ops_dir, 'mozart/ops/s3-bucket-listing')
    index_file = os.path.join(repo_dir, 'tmp_index.html')
    list_js = os.path.join(repo_dir, 'list.js')
    index_style = os.path.join(repo_dir, 'index-style')
    upload_template('s3-bucket-listing.html.tmpl', index_file, use_jinja=True, 
                    context=ctx, template_dir=get_user_files_path())
    if encrypt is False:
        run('aws s3 cp %s s3://%s/index.html' % (index_file, bucket))
        run('aws s3 cp %s s3://%s/' % (list_js, bucket))
        run('aws s3 sync %s s3://%s/index-style' % (index_style, bucket))
    else:
        run('aws s3 cp --sse %s s3://%s/index.html' % (index_file, bucket))
        run('aws s3 cp --sse %s s3://%s/' % (list_js, bucket))
        run('aws s3 sync --sse %s s3://%s/index-style' % (index_style, bucket))


##########################
# create cloud function zip
##########################

def create_zip(zip_dir, zip_file):
    if exists(zip_file): run('rm -rf %s' % zip_file)
    with cd(zip_dir):
        run('zip -r -9 {} *'.format(zip_file))
