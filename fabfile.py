import smtplib, logging, logging.handlers, time, conf
from time import time
from datetime import datetime, time, date, timedelta
from fabric.api import *
from fabric.network import *
from fabric.contrib import *
from fabric.colors import *

"""
Base configuration
"""
env.project_name = 'your_projectname'
env.user = 'sshuser'
env.dbname = 'projectname_drupal_'+datetime.now().strftime('%Y-%m-%d-%H-%M')
env.roledefs = {
    'db': ['10.10.10.1'],
    'bo': ['10.10.10.2'],
    'dev': ['10.10.10.3'],
    'live': ['10.10.10.4', '10.10.10.5', '10.10.10.6', '10.10.10.7'],
}

"""
Environments
"""
@task
def web3():
    """
    Work on web3 environment
    """
    env.settings = 'web3'
    env.hosts = ['10.10.10.6']
    env.docroot = '/var/www/html'

@task
def live():
    """
    Work on live environment
    """
    env.settings = 'live'
    env.hosts = ['10.10.10.4', '10.10.10.5', '10.10.10.6', '10.10.10.7']
    env.docroot = '/var/www/html'

@task
def backoff():
    """
    Work on backoffice environment
    """
    env.settings = 'backoff'
    env.hosts = ['10.10.10.2']
    env.gitdir = '/root/your_project/code'
    env.docroot = '/var/www/html'
    env.current_path = '/root/your_project/current'
    env.releases_path = '/root/your_project/releases'
    env.release_date = datetime.now().strftime('%Y%m%d%H%M%S')
    env.branch = 'master'

@task
def staging():
    """
    Work on staging environment
    """
    env.settings = 'staging'
    env.hosts = ['10.10.10.3']
    env.gitdir = '/root/your_project_staging'
    env.docroot = '/var/www/html'
    env.branch = 'staging'

@task
def develop():
    """
    Work on develop environment
    """
    env.settings = 'develop'
    env.hosts = ['10.10.10.3']
    env.gitdir = '/root/yor_project_dev'
    env.docroot = '/var/www/vhosts/your_project/httpdocs'
    env.branch = 'develop'

"""
Branches
"""
def branch(branch_name):
    """
    Work on any specified branch.
    """
    env.branch = branch_name

"""
Deployment
"""
@task
def deploy():
    """
    Deploy latest git code to server. Syntax: fab <backoff/staging/develop> deploy
    """
    require('settings', provided_by=[backoff, staging, develop])

    if '10.10.10.2' in env.hosts:
        #set start deploy time
        start = time.time()

    with cd('%(gitdir)s' % env):
        #set latest project release path
        env.current_path = env.gitdir

        #pulling latest code to live
        pulled = run('git pull origin %(branch)s' % env)
        print (green('Pulled in latest changes on branch %(branch)s', bold=True) % env)

        if '10.10.10.3' in env.hosts:
            env.current_release = '%(releases_path)s/%(release_date)s' % env
            run('cp -rp %(gitdir)s %(current_release)s' % env)

            print (green('Completed mounting latest release', bold=True))
            pulled += "\n\n"
            pulled += "Latest release path: " + str(env.current_release)
            pulled += "\n\n"

            #make a symlink to a latest release and cleanup old releases.
            symlink()

    #run local rsync
    local_rsync()

    #clear drupal cache
    clear_cache()
    print(green('Finished drush cc all', bold=True))

    if '10.10.10.2' in env.hosts:
        #sync from bo to web1/web2/web3
        rsynced = rsync()

        pulled += "\n\n"
        pulled += "Rsync log dump:"
        pulled += "\n\n"
        pulled += str(rsynced)

        print(green('Finished remote rsync', bold=True))

        #get end deploy time
        end = time.time()
        #deploy run time
        deploy_time = end - start

        #send mail on success
        _send_mail(pulled, deploy_time, env.host)

"""
Rollback
"""
@task
@roles('bo')
def rollback():
    """
    Rolls back to the previously deployed version.
    """
    #set start deploy time
    start = time.time()

    #set env and vars for rollback
    backoff()
    releases()

    if len(env.releases) >= 2:
        env.current_release = env.releases[-1]
        env.previous_revision = env.releases[-2]
        env.current_release = '%(releases_path)s/%(current_revision)s' % env
        env.previous_release = '%(releases_path)s/%(previous_revision)s' % env
        pulled  = "\n\n"
        pulled += run('rm %(current_path)s; ln -s %(previous_release)s %(current_path)s && rm -rf %(current_release)s' % env)
        pulled += "\n\n"


    #run local rsync
    local_rsync()

    #clear drupal cache
    clear_cache()
    print(green('Finished drush cc all', bold=True))

    #run remote sync from bo to web1/web2/web3
    rsynced = rsync()

    pulled += "\n\n"
    pulled += "Rsync log dump:"
    pulled += "\n\n"
    pulled += str(rsynced)

    print(green('Finished remote rsync', bold=True))

    #get end deploy time
    end = time.time()
    #deploy run time
    deploy_time = end - start

    #send mail on success
    _send_mail(pulled, deploy_time, env.host, 'rollback')

"""
Commands - miscellaneous
"""
@roles('bo')
def symlink():
    """
    Updates the symlink to the most recently deployed version.
    """
    releases()
    env.current_path = '/root/your_project/current'
    run('rm %(current_path)s' % env)
    run('ln -s %(current_release)s %(current_path)s' % env)

@roles('bo')
def rsync():
    """
    Run remote rsync from backoff to WEB1/WEB2/WEB3.
    """
    rsynced = run('/rsync/rsync-WWW-from-BO-to-WEB1-WEB2-WEB3.sh')
    return rsynced

@roles('bo', 'dev')
def local_rsync():
    """
    Run local rsync from home to docroot.
    """
    with cd('%(current_path)s' % env):
        print(green('Running local rsync', bold=True))
        run('rm -f sites/default/settings.php')
        run('rsync -a sites/all/ %(docroot)s/sites/all/ --delete' % env)
        print(green('Finished local rsync', bold=True))


@roles('bo')
def cleanup():
    """Clean up old releases"""
    if len(env.releases) > 3:
        directories = env.releases
        directories.reverse()
        del directories[:3]
        env.directories = ' '.join([ '%(releases_path)s/%(release)s' % { 'releases_path':env.releases_path, 'release':release } for release in directories ])
        run('rm -rf %(directories)s' % env)

@roles('bo')
def releases():
    """
    List a releases made.
    """
    r = run('ls -x %(releases_path)s' % env)
    env.releases = sorted(r.split("\t"))
    if len(env.releases) >= 1:
        env.current_revision = env.releases[-1]
        env.current_release = '%(releases_path)s/%(current_revision)s' % env
    if len(env.releases) > 1:
        env.previous_revision = env.releases[-2]
        env.previous_release = '%(releases_path)s/%(previous_revision)s' % env

    #cleanup old releases. max 3 allowed.
    cleanup()

@task
def prepare_deploy():
    """
    Prepare enviroment for deployment. Fix perms,..
    """
    with cd('/srv/http/your_project'):
        #check && fix file perms
        local('''find . -type f -exec chmod -x {} \;''')
        local('''git commit -a -m "fixed perms"''')


@task
@parallel
@roles('live')
def restart_apache():
    """
    Restart the Apache2 server.
    """
    run('/etc/init.d/httpd restart')
    print(cyan('Apache restarted on live servers', bold=True))

@task
@parallel
@roles('live')
def restart_varnish():
    """
    Restart the Varnish server.
    """
    run('/etc/init.d/varnish restart')
    print(cyan('Varnish restarted on live servers', bold=True))

@task
@roles('dev')
def restart_vh():
    """
    Restart the Apache and Varnish on Dev server.
    """
    run('/etc/init.d/httpd restart')
    print(green('Apache has been restarted on dev server', bold=True))
    run('/etc/init.d/varnish restart')
    print(green('Varnish has been restarted on dev server', bold=True))

@task
@parallel
def shm_status():
    """
    Get SHM translation state on servers. Syntax: fab <backoff/live/staging/develop> shm_status
    """
    require('settings', provided_by=[backoff, live, staging, develop])

    with cd('%(docroot)s' % env):
        line = run('cat sites/default/settings.php |grep locale')
    print(cyan('Translation state :::  ' + line, bold=True))

@task
@parallel
def shm_disable():
    """
    Disable SHM translation state on servers. Syntax: fab <backoff/live/staging/develop> disable_shm
    """
    require('settings', provided_by=[backoff, live, staging, develop])

    with cd('%(docroot)s' % env):
        files.comment('sites/default/settings.php','''"your_project_locale"''')
        line = run('cat sites/default/settings.php |grep locale')
    print(red('Translation strings used from db :::  ' + line, bold=True))


@task
@parallel
def shm_enable():
    """
    Enable SHM translation state on servers. Syntax: fab <backoff/live/staging/develop> enable_shm
    """
    require('settings', provided_by=[backoff, live, staging, develop])

    with cd('%(docroot)s' % env):
        files.uncomment('sites/default/settings.php','''"your_project_locale"''')
        line = run('cat sites/default/settings.php |grep locale')
    print(cyan('Translation strings used from SHM :::  ' + line, bold=True))

@task
def shm_sync():
    """
    Synchronize translation strings from db to SHM. Syntax: fab <backoff/live/staging/develop> shm_sync
    """
    require('settings', provided_by=[backoff, live, staging, develop])

    print(cyan('Synchronizing translations strings to ram ..'))
    with cd('%(docroot)s' % env):
        run('''ipcs -m | awk ' $3 == "apache" {print $2, $3}' | awk '{ print $1}' | while read i; do ipcrm -m $i; done''')
        print(green('Wiped all translation strings from shm', bold=True))
        message = run('''su apache -c 'drush shm-update';''')
    print(green('Translations synchronized', bold=True))

    msg = "Subject: Translation strings synced on "+env.host+"\n"
    msg += "\n"
    msg += message
    msg += "\n\n"

    s = smtplib.SMTP('localhost')
    s.sendmail('shm-strings', conf.to_addrs, msg)
    s.quit()

@task
def clear_cache():
    """
    Selectively wipe drupal cache by choosing a category you want to clear. Syntax: fab <backoff/web3/staging/develop> clear_cache
    """
    require('settings', provided_by=[backoff, web3, staging, develop])

    with cd('%(docroot)s' % env):
        run('drush cc')
    print(green('Drupal cache cleared', bold=True))

@task
def clear_cache_all():
    """
    Wipe all drupal cache tables without confirmation. Syntax: fab <backoff/live/staging/develop> clear_cache_all
    """
    require('settings', provided_by=[backoff, live, staging, develop])

    with cd('%(docroot)s' % env):
        run('drush cc all -y')
    print(green('Drupal cache cleared', bold=True))

@task
@parallel
@roles('live')
def clear_varnish_hp():
    """
    Wipe homepage from varnish.
    """
    run('varnishadm ban.url "^/$"')
    print(cyan('Homepage deleted from varnish vache', bold=True))

@task
@parallel
@roles('live')
def clear_varnish_url(url):
    """
    Wipe specified varnish object. Syntax: fab clear_varnish_url:<url>
    """
    run('varnishadm ban.url "^%s"' % url)
    print(cyan('Wiped "%s" page from varnish vache', bold=True) % url)


"""
Commands - data
"""
@task
@roles('db')
def sql_state(full=None):
    """
    Print the number of active sql processes and full processlist.
    """
    if full:
        run('mysql -e "show full processlist\G"')
        print(cyan('Number of SQL processes: ' + run('mysql -e "show processlist"| grep -i query |wc -l')))
    else:
        run('mysql -e "show full processlist"')
        print(cyan('Number of SQL processes: ' + run('mysql -e "show processlist"| grep -i query |wc -l')))


@roles('db')
def import_db(live, dev):
    """
    Imports database from sql cluster to dev server. Usage: fabric import_db:<live-db-name>,<dev-db-name>

    """
    with settings(warn_only=True):
        if live and dev:
            #dump db and it's cache table structure to tmp dir
            run('mysqldump --ignore-table="%s".cache --ignore-table="%s".cache_block --ignore-table="%s".cache_content --ignore-table="%s".cache_filter --ignore-table="%s".cache_form --ignore-table="%s".cache_menu --ignore-table="%s".cache_objects --ignore-table="%s".cache_page --ignore-table="%s".cache_path --ignore-table="%s".cache_views --ignore-table="%s".cache_views_data "%s" > /tmp/%(dbname)s.sql' % live, env)
            run('mysqldump -d "%s" cache cache_block cache_content cache_filter cache_form cache_menu cache_objects cache_page cache_path cache_views cache_views_data > /tmp/cache_structure.sql' & live)
            print(green('Database and cache table structure successfuly dumped to /tmp dir on sql cluster', bold=True))

            #copy db and cache structure to dev server
            run('scp /tmp/%(dbname)s.sql root@10.10.10.1:/var/lib/mysql/' % env)
            run('scp /tmp/cache_structure.sql root@10.10.10.1:/var/lib/mysql/')
            print(green('Database and cache table structure successfuly copied to dev server', bold=True))

            #remove tmp sql dump and cache structure
            run('rm -rf /tmp/%(dbname)s.sql' % env)
            run('rm -rf /tmp/cache_structure.sql')
            print(green('Database and cache table structure successfuly removed from /tmp dir on sql cluster', bold=True))

            #switch to dev server and import db
            env.host = ['10.10.10.1']

            #import db on dev server and create missing cache_form table
            run('mysql -p "%s" < /var/lib/mysql/%(dbname)s.sql' % dev, env)
            run('mysql -p "%s" < /var/lib/mysql/cache_structure.sql')
            print(green('Database and cache table structure successfuly imported on dev server', bold=True))

            #remove local copy of sql dump and cache structure
            run('rm -rf /var/lib/mysql/%(dbname)s.sql' % env)
            run('rm -rf /var/lib/mysql/cache_structure.sql')
            print(green('Database and cache table structure successfuly removed from /var/lib/mysql/ dir on dev server', bold=True))

            print(green('Finished import on dev server', bold=True))
        else:
            print(red('You must enter database name of live and dev server', bold=True))
            print(red('Usage:  fabric import_db:<live-db-name>,<dev-db-name>', bold=True))

"""
Utility functions (not to be called directly)
"""
logging.basicConfig( level=logging.INFO )
def _insert_log(message):
    sys_logger = logging.getLogger('deploy')
    sys_logger.setLevel(logging.ERROR)
    handler = logging.handlers.SysLogHandler(address = '/dev/log')
    sys_logger.addHandler(handler)
    sys_logger.debug(message)

def _send_mail(message, deploy_time, host, mailtype=None):

    if mailtype is None:
        msg = "Subject: Latest code deployed on "+host+"\n"
        msg += "\n"
        msg += message
        msg += "\n\n"
        msg += "Deployment lasted for "+ str(timedelta(seconds=int(deploy_time)))

        _insert_log("Latest code deployed on "+host+" :::"+datetime.now().strftime('%Y-%m-%d %H:%M'))

        s = smtplib.SMTP('localhost')
        s.sendmail('deploy', conf.to_addrs, msg)
        s.quit()
    else:
        msg = "Subject: Rolledback to previous version of code on "+host+"\n"
        msg += "\n"
        msg += message
        msg += "\n\n"
        msg += "Rollback lasted for "+ str(timedelta(seconds=int(deploy_time)))

        _insert_log("Rolledback code on "+host+" :::"+datetime.now().strftime('%Y-%m-%d %H:%M'))

        s = smtplib.SMTP('localhost')
        s.sendmail('deploy', conf.to_addrs, msg)
        s.quit()

