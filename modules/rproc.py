import os
import sys
import random
import time
import cPickle
import subprocess
import math
import pdb
import inspect
import types
import imp

### define globals
rproc_nqstat_time = None
rproc_nqstat_output = None
MATLAB_RETURN_VALUE = None
THIS_IS_A_RPROC_PROCESS = None
rproc_wait_jobinfo = None

#### define jobinfo class
class Jobinfo():

    def __init__(self):
        
        self.ProcName = []
        self.P1 = []
        self.Mem = []
        self.options = dict()
        self.time = None
        self.prefix = []
        self.mat_fname = ''
        self.result_fname = ''
        self.m_fname = ''
        self.log_fname = ''
        self.qsublog_fname = ''
        self.jobid = -1
        self.submission_time = None
        self.retries = 0
        self.created = 0
        self.time_of_loss = None
        self.crashed_time = None
        self.maxvmem = None
        self.resubmit = False
        self.time_req_resubmit = []
        self.mem_req_resubmit = []
        self.data_size = []
        self.start_time = []
        self.hard_time_limit = 1000000
        self.callfile = None

### define Error class
class RprocRerun(Exception):
    
    def __init__(self, string):
        
        self.string = string

    def __str__(self):
        
        return repr(self.string)

def rproc(ProcName, P1, Mem=None, options=None, runtime=None, callfile=None, resubmission=False):
    # [jobinfo]=rproc(ProcName, P1, Mem, options, time)
    #
    # time in minutes
    # mem in mb

    environment = '' # TODO

    if callfile is None:
        ### check if ProcName is defined in calling function
        callframe = sys._getframe(1)
        if not ProcName in callframe.f_locals:
            if not ProcName in callframe.f_globals:
                print >> sys.stderr, 'ERROR: Could find no definition for %s in local or global context of calling function. Use kword callfile to specify file where %s is defined. Use the relative path to the location of the calling function!' % (ProcName, ProcName)
                return 
            else:
                callfile = (callframe.f_globals[ProcName].__module__, inspect.getfile(callframe.f_globals[ProcName]))
        else:
            callfile = (callframe.f_locals[ProcName].__module__, inspect.getfile(callframe.f_locals[ProcName]))

    ### detect path of this script
    this_frame = sys._getframe(0)
    rproc_path = os.path.abspath(inspect.getfile(this_frame))

    if runtime is None:
        runtime = 10000

    if Mem is None:
        Mem = 300

    if Mem < 100:
        print >> sys.stderr, 'WARNING: You specified to allocate less than 100Mb memory for your job. This might not be enough to start. Re-setting to 100Mb'
        Mem = 100

    if options is None:
        options = dict()

    ### get module list of caller to re-create environment
    if not 'imports' in options:
        options['imports'] = dict()
    if not resubmission:
        callframe = sys._getframe(1)
        #options['package'] = os.path.dirname(os.path.abspath(callframe.f_globals['__file__']))
        for l in callframe.f_globals:
            if (len(l) < 2 or l[:2] != '__'):
                if isinstance(callframe.f_globals[l], types.ModuleType):
                    if not l in options['imports']:
                        if imp.is_builtin(callframe.f_globals[l].__name__) != 0:
                            options['imports'][l] = (callframe.f_globals[l].__name__, 'builtin') 
                        else:
                            options['imports'][l] = (callframe.f_globals[l].__name__, callframe.f_globals[l].__file__) 

    if not callfile[0] in options['imports']:
        options['imports'][callfile[0]] = callfile

    home_str = os.environ['HOME'] 

    use_reservation = False

    ### TODO this is only relevant for SGE
    if 'ncpus' in options and options['ncpus'] > 1:
        Mem /= options['ncpus']
        use_reservation = 1 ;

    if not 'verbosity' in options:
        options['verbosity'] = True
    if not 'maxjobs' in options:
        options['maxjobs'] = 3000
    if not 'waitonfull' in options:
        options['waitonfull'] = True
    if not 'immediately' in options:
        options['immediately'] = False
    if not 'immediately_bg' in options:
        options['immediately_bg'] = False
    if not 'submit_now' in options:
        options['submit_now'] = True
    if not 'nicetohave' in options:
        options['nicetohave'] = False
    if not 'ncpus' in options:
        options['ncpus'] = 1
    if not 'start_dir' in options:
        dirctry = os.getcwd()
    else:
        dirctry = options['start_dir'] 
    if not 'resubmit' in options:
        options['resubmit'] = False
        options['time_req_resubmit'] = []
        options['mem_req_resubmit'] = []
    if not 'data_size' in options:
        options['data_size'] = [] 
    if not 'hard_time_limit' in options:
        options['hard_time_limit'] = 1000000

    jobinfo = rproc_empty()

    jobinfo.ProcName = ProcName
    jobinfo.P1 = P1
    jobinfo.Mem = Mem
    jobinfo.options = options
    jobinfo.time = runtime
    jobinfo.created = True
    jobinfo.resubmit = options['resubmit']
    jobinfo.mem_req_resubmit = options['mem_req_resubmit']
    jobinfo.time_req_resubmit = options['time_req_resubmit']
    jobinfo.data_size = options['data_size']
    jobinfo.hard_time_limit = options['hard_time_limit']

    if not os.path.exists(os.path.join(os.environ['HOME'], 'tmp', '.sge')):
        username = os.environ['USER']
        base_dir = os.path.join(home_str, '.sge.', 'tmp', username)
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

        tmp_dir = os.path.join(home_str, '.sge', 'tmp', username, 'tmp')
        if not os.path.exists(tmp_dir):
            os.makedirs(tmp_dir)

        sge_dir = os.path.join(home_str, '.sge', 'tmp', username, 'sge')
        if not os.path.exists(sge_dir):
            os.makedirs(sge_dir)

        if not os.path.exists(os.path.join(os.environ['HOME'], 'tmp')):
            os.makedirs(os.path.join(os.environ['HOME'], 'tmp'))

        if not os.path.exists(os.path.join(os.environ['HOME'], 'tmp', '.sge')):
            os.symlink(sge_tmp_dir, os.path.join(os.environ['HOME'], 'tmp', '.sge'))

    assert(os.path.exists(os.path.join(os.environ['HOME'],'tmp', '.sge')))

    if not os.path.exists(os.path.join(dirctry, '.sge')):
        username = os.environ['USER']
        sge_base_dir = dirctry.replace(os.path.join('cbio', 'grlab', 'home', username), os.path.join(home_str, '.sge', 'tmp', username))
        if not os.path.exists(sge_base_dir):
            os.makedirs(sge_base_dir)

        sge_dir = os.path.join(sge_base_dir, 'sge')
        os.makedirs(sge_dir)
        
        os.symlink(sge_dir, os.path.join(dirctry, '.sge'))


    ### assembly option string
    if use_reservation:
        option_str = ' -R y'
    else:
        option_str = ''
     
    #option_str += ' -l h_vmem=%iM -l s_vmem=%iM -soft -l h_cpu=%1.0f -hard ' % (Mem, Mem,  max(60, runtime*60))
    option_str += '-l nodes=1:ppn=%i -l mem=%imb,vmem=%imb,pmem=%imb -l walltime=%1.0f' % (options['ncpus'], Mem, Mem,  Mem, max(60, runtime*60))

    if environment == 'galaxy':
        option_str += ' -l parent=0.0 '

    if 'hold' in options:
        if options['hold']: 
            option_str += ' -h u'
    if 'queue' in options:
        option_str += ' -q "%s" ' % options['queue']
    if 'nicetohave' in options and options['nicetohave']:
        option_str += ' -l nicetohave=1'

    if 'priority' in options:
        option_str += ' -p %i' % options['priority']

    if 'express' in options and options['express']:
        option_str += ' -l express'

    if 'hostname' in options:
        option_str += '%s -l hostname=%s' % (option_str, options['hostname'])

    ### TODO make this configurable
    bin_str = 'python'

    ### request cplex license
    if 'cplex' in options and options['cplex']:
        option_str += ' -l cplex=1'

    ### request several cpus
    #if 'ncpus' in options and options['ncpus'] > 1:
    #    option_str += ' -pe "*" %i ' % options['ncpus']

    if 'identifier' in options:
      identifier = options['identifier']
    else:
      identifier = 'RP' ;

    cc = random.randint(0, 100000)
    prefix = '%s%i-%1.10f' % (identifier, cc, time.time())
    rproc_dir = '%s/tmp/.sge' % os.environ['HOME']
    mat_fname = os.path.join(rproc_dir, '%s.pickle' % prefix) 
    result_fname = os.path.join(rproc_dir, '%s_result.pickle' % prefix)
    m_fname = os.path.join(rproc_dir, '%s.sh' % prefix)
    while os.path.exists(mat_fname) or os.path.exists(result_fname) or os.path.exists(m_fname):
        cc = random.randint(0, 100000)
        prefix = '%s%i-%1.10f' % (identifier, cc, time.time())
        mat_fname = os.path.join(rproc_dir, '%s.pickle' % prefix) 
        result_fname = os.path.join(rproc_dir, '%s_result.pickle' % prefix)
        m_fname = os.path.join(rproc_dir, '%s.sh' % prefix)

    if 'log_fname' in options:
        log_fname = options['log_fname']
    else:
        log_fname = os.path.join(dirctry, '.sge', '%s_%s.rproc' % (prefix, time.strftime('%d-%b-%Y_%H_%M')))
    qsublog_fname = '%s.qsubout' % log_fname

    jobinfo.prefix = prefix 
    jobinfo.mat_fname = mat_fname 
    jobinfo.result_fname = result_fname 
    jobinfo.m_fname = m_fname 
    jobinfo.log_fname = log_fname 
    jobinfo.qsublog_fname = qsublog_fname 
    jobinfo.callfile = callfile

    ### save the call information
    cPickle.dump((ProcName, P1, dirctry, options, callfile), open(mat_fname, 'wb'), -1)

    evalstring = '%s %s %s' % (bin_str, rproc_path, mat_fname)
    evalstring = 'cd %s; %s; exit' % (dirctry, evalstring)
    fd = open(m_fname, 'w')
    print >> fd, '%s' % evalstring
    fd.close()

    if 'envstr' in options:
        envstr = options['envstr']
        if len(envstr) > 0:
          envstr += ';' 
    else:
        envstr = '' 

    if options['immediately']:
        str = '%s bash %s >> %s' % (envstr, m_fname, log_fname)
    elif options['immediately_bg']:
        str = '%s bash %s >> %s &' % (envstr, m_fname, log_fname)
    else:
      #str = 'echo \'%s hostname; bash %s >> %s\' | qsub -o %s -j y -r y %s -N %s >> %s 2>&1' % (envstr, m_fname, log_fname, qsublog_fname, option_str, prefix, log_fname)
      str = 'echo \'%s hostname; bash %s >> %s\' | qsub -o %s -j oe -r y %s -N %s >> %s 2>&1' % (envstr, m_fname, log_fname, qsublog_fname, option_str, prefix, log_fname)

    ### too verbose
    #if options['submit_now'] and options['verbosity']:
    #    print str

    # wait until we are allowed to submit again, i.e. #jobs < maxjobs
    if not options['immediately'] and not options['immediately_bg'] and options['waitonfull']:
        while True:
            try:
                num_queued = int(subprocess.check_output('qstat -u' + os.environ['USER'] + '2> /dev/null | grep ' + os.environ['USER'] + '| wc -l | tr -d " "', shell=True).strip())
            except:
                print >> sys.stderr, 'WARNING: could not determine how many jobs are scheduled'
                break
            
            # keep 50 spare jobs if multiple rprocs are scheduling...
            if (num_queued < options['maxjobs']):
                break
            else:
                if options['verbosity']:
                    print >> sys.stdout, 'queue full, sleeping 60 seconds (%i/%i)' %(num_queued, options['maxjobs'])
                time.sleep(60)

    if options['submit_now']:
        if options['immediately'] and options['verbosity']:
            print >> sys.stdout, 'immediatedly starting job on local machine'
        if options['immediately_bg'] and options['verbosity']:
            print >> sys.stdout, 'immediatedly starting job on local machine in background'

        if options['immediately_bg']:
            while True:
                str_ = subprocess.check_output('uptime').strip()
                float(str_[re.search('average:', str_).start()+8:].split(',')[0])
                hit = re.search('average:', str_)
                while hit is None:
                    hit = re.search('average:', str_)
                idx = hit.start() 
                cpu_load = float(str_[idx+8:].split(',')[0])
                if cpu_load > 13:
                    if options['verbosity']:
                        print 'load too high: %1.2f' % cpu_load
                    time.sleep(10)
                else:
                    break
            time.sleep(2)
      
        p1 = subprocess.Popen(['echo', str], stdout=subprocess.PIPE)
        p2 = subprocess.Popen(['bash'], stdin=p1.stdout, stdout=subprocess.PIPE)
        p2.communicate()
        ret = p2.returncode
        if ret != 0:
            print >> sys.stderr, 'submission failed:\n\tsubmission string: %s\n\treturn code: %i' % (str, ret)
        jobinfo.submission_time = time.time()
      
        if not options['immediately'] and not options['immediately_bg']:
            fd = open(log_fname, 'r')
            jobinfo.jobid = -1
            if fd:
              s = fd.read().strip()
              items = s.split('.')
              if not ((items[1] == 'mskcc-fe1') and (items[2] == 'local')):
                  print >> sys.stderr, str
                  print >> sys.stderr, 'ERROR: submission failed: %s' % s
                  sys.exit(1)
              jobinfo.jobid = int(items[0])
              fd.close()
      
              rproc_register('submit', jobinfo)
        else:
            jobinfo.jobid = 0 
    else:
        jobinfo.jobid = 0 

    return jobinfo


def finish():

    print 'rproc finishing'

    global MATLAB_RETURN_VALUE

    if MATLAB_RETURN_VALUE is not None:
        print 'exit code %i' % MATLAB_RETURN_VALUE
        try:
            rf = os.environ['MATLAB_RETURN_FILE']
            fd = fopen(rf, 'w+')
            if fd:
                print >> fd, '%i', MATLAB_RETURN_VALUE[0]
            fclose(fd) ;
        except KeyError:
            print >> sys.stderr, 'WARNING: environment MATLAB_RETURN_FILE not defined'

def rproc_clean_register():

    fname = os.path.join(os.environ['HOME'], 'tmp', 'rproc.log')

    jobids = []
    parent_jobids = []

    fd = open(fname, 'r')
    for line in fd:
        if len(line.strip()) == 0:
            continue

        items = line.split()
        if len(items) < 4:
            continue
        if len(items[0]) == 0:
            continue
        if len(items[3]) == 0:
            continue
        if items[0][0] >= '0' and items[0][0] <= '9' and ((items[3][0] >= '0' and items[3][0] <= '9') or items[3][0] == '-'):
            jobids.append(int(items[0]))
            parent_jobids.append(int(items[3]))


    text = subprocess.check_output('qstat').strip()
    for line in text.split('\n'):
        items = line.split(' ')
        if items[0][0] >= '0' and items[0][0] <= '9':
            running_jobids.append(int(items[0]))
            
    idx = [i for i in range(len(jobids)) if jobids[i] in running_jobids]

    for i in range(len(idx)):
        if not parent_jobids[idx[i]] in running_jobids and parent_jobids[idx[i]] != -1:
            print >> sys.stderr, 'job %i is still running, but the parent job %i not' % (jobids[idx[i]], parent_jobids[idx[i]])

def rproc_cleanup(jobinfo):
  
    for ix in  range(len(jobinfo)):
        command = 'rm -f %s %s %s %s %s' % (jobinfo[ix].mat_fname, jobinfo[ix].result_fname,
                                            jobinfo[ix].m_fname, jobinfo[ix].log_fname, 
                                            jobinfo[ix].qsublog_fname)
        subprocess.call(command.split(' '))

        rproc_register('cleanup', jobinfo[ix])


def rproc_cmd(unix_cmd, jobinfo):

    for i in range(len(jobinfo)):
        if len(jobinfo[i].jobid) > 0 and jobinfo[i].jobid != -1:
            subprocess.call([unix_cmd, jobinfo[i].jobid])


def rproc_create(ProcName, P1, Mem=100, options=[], runtime=144000):
    # [jobinfo]=rproc(ProcName, P1, Mem, options, time)
    #
    # time in minutes
    # mem in mb
  
    jobinfo = rproc_empty()

    jobinfo.ProcName = ProcName
    jobinfo.P1 = P1
    jobinfo.Mem = Mem
    jobinfo.options = options
    jobinfo.time = runtime

    jobinfo.created = True
    jobinfo.retries = -1

    return jobinfo

def rproc_empty(N = None):
    """Create jobinfo list"""
  
    if N is None:
        N = 1

    if N > 1:
        jobinfo = [] 
        for i in range(N):
            jobinfo.append(Jobinfo())
    else:
        jobinfo = Jobinfo()

    return jobinfo

def rproc_finished(jobinfo):
    # isfinished = rproc_finished(jobinfo) ;

    if jobinfo.jobid == -1:
        return False
    if os.path.exists(jobinfo.result_fname):
        rproc_register('finished', jobinfo)
        return True
    return False


def rproc_kill(jobinfo):

    if jobinfo == 'wait':
        global rproc_wait_jobinfo
        jobinfo = rproc_wait_jobinfo

    for i in range(len(jobinfo)):  
        if len(jobinfo[i].jobid) and jobinfo[i].jobid > 0:
            subprocess.call('qdel', jobinfo[i].jobid, '2>', '/dev/null')
            rproc_register('kill', jobinfo[i])

def rproc_reached_timelimit(jobinfo):
    # [result, jobwalltime] = rproc_reached_timelimit(jobinfo)

    #str_ = 'qacct -j %i | grep ru_wallclock|sed \'s/ru_wallclock//g\'' % jobinfo.jobid
    str_ = 'qstat -f %i | grep resources_used.walltime | sed -e "s/.*= //g"' % jobinfo.jobid
    w = subprocess.check_output(str_, shell=True)
    ## TODO use save Popen for pipeline

    if 'error' in w:
        return (False, -1)

    try:
        jobwalltime = split_walltime(w.strip()) # get time in seconds
    except Exception:
        return (False, -1) 

    if not (jobwalltime > 0 and jobwalltime < 36000000): # sanity checks
        print >> sys.stderr, 'WARNING: invalid output from qacct'
        return (False, -1) 

    if jobwalltime > (jobinfo.time * 60):
        return (True, jobwalltime)
    else:
        return (False, jobwalltime)

def rproc_register(action, jobinfo):

    try:
        this_jobid = int(os.environ['JOB_ID'])
    except:
        this_jobid = -1

    rproc_log_fname = os.path.join(os.environ['HOME'], 'tmp', 'pyproc.log')

    if not os.path.exists(rproc_log_fname):
      fd = open(rproc_log_fname, 'a+')
      print >> fd, '# prefix\taction\tparent jobid\tjobid\tfunction\ttime'
      fd.close()

    fd = open(rproc_log_fname, 'a+')
    print >> fd, '%i\t%s\t%s\t%i\t%s\t%s' % (jobinfo.jobid, jobinfo.prefix, action, this_jobid, jobinfo.ProcName, time.asctime()) #time.strftime('%a_%b_%d_%Y_%H:%M:%S'))
    fd.close()

def rproc_rerun(mess=''):

    global MATLAB_RETURN_VALUE
    MATLAB_RETURN_VALUE=99
    global THIS_IS_A_RPROC_PROCESS  
      
    if THIS_IS_A_RPROC_PROCESS is not None and THIS_IS_A_RPROC_PROCESS == 1:
        sys.exit
    else:
        raise RprocRerun(mess)

def rproc_resubmit(jobinfo, force=True):
# jobinfo2 = rproc_resubmit(jobinfo);

    if jobinfo is None:
        return jobinfo
    elif isinstance(jobinfo, list):
        jobinfo2 = jobinfo
        for i in range(len(jobinfo)):
            jobinfo2[i] = rproc_resubmit(jobinfo[i])
        return jobinfo2
      
    if (jobinfo.retries >= 0) and (rproc_time_since_submission(jobinfo) < 1):
        #warning('job was submitted less than a minute ago. not resubmitted.') ;
        return jobinfo

    if jobinfo.retries >= 3:
        if jobinfo.options['verbosity'] >= 0:
            print >> sys.stderr, 'Warning: job has already been submitted %i times' % jobinfo.retries
        if jobinfo.options['verbosity'] > 0:
            print 'check file %s' % jobinfo.log_fname
        return jobinfo

    if (jobinfo.retries >= 0):
        (still_running, qstat_line, start_time, status) = rproc_still_running(jobinfo)
        if still_running: 
            if jobinfo.options['verbosity'] > 0:
                print >> sys.stdout, '.',
            jobinfo2 = jobinfo
            jobinfo2.time_of_loss = None
            return jobinfo2
        if jobinfo.time_of_loss is None:
            jobinfo.time_of_loss = time.time()
        # more than a minute lost?
        if not force and  ((jobinfo.time_of_loss - time.time() / 60) < 1):
            #warning('do not resubmit yet ... ') ;
            jobinfo2 = jobinfo
            return jobinfo2
        #rproc_cleanup(jobinfo)

    #fprintf('\nresubmitting job\n') ;
    jobinfo2 = rproc(jobinfo.ProcName, jobinfo.P1, jobinfo.Mem, jobinfo.options, jobinfo.time, jobinfo.callfile, resubmission=True)

    if jobinfo.jobid != -1:
        # increase only, if it has not been resubmitted before
        jobinfo2.retries = jobinfo.retries + 1

    return jobinfo2

def rproc_result(jobinfo, read_attempts=None):
# [retval1, retval2] = rproc_result(jobinfo, [read_attempts])
  
    if not os.path.exists(jobinfo.result_fname):
        att = 1
        while not os.path.exists(jobinfo.result_fname):
            print >> sys.stdout, 'Job not finished yet. Waiting for result file to appear.'
            if read_attempts is not None and att > read_attempts:
                error('Unable to load result from %s', jobinfo.result_fname);
            time.sleep(10)
            att += 1 

    (retval1, retval2) = cPickle.load(open(jobinfo.result_fname, 'r'))

    return (retval1, retval2)


def rproc_still_running(jobinfo):
# [still_running, line, start_time, status] = rproc_still_running(jobinfo);

    status = 0
    still_running = 0
    global rproc_nqstat_output
    global rproc_nqstat_time
    start_time = []
    if jobinfo.jobid == 0:
        # runs locally in background
        still_running =  not rproc_finished(jobinfo)
        line = 'local job %s is still running: %s\n' % (jobinfo.prefix, jobinfo.log_fname)
        return (still_running, line, start_time, status)

    curtime = time.time()
    if rproc_nqstat_time is None or (curtime - rproc_nqstat_time > 0.5e-4):
        try:
            text = subprocess.check_output(['qstat', '-u', os.environ['USER']])
            rproc_nqstat_output = text
            rproc_nqstat_time = curtime
        except CalledProcessError as e:
            if e.returncode == 130:
                print >> sys.stderr, 'rproc_still_running interupted by user'
                status = -1
                line = ''
                start_time = ''
            print >> sys.stderr, 'WARNING: qstat failed'
    else:
        text = rproc_nqstat_output
    
    for line in text.strip().split('\n'):
        if len(line) > 0:
            items = line.split(' ')
            if not os.environ['USER'] in items:
                continue
            for j in range(len(items)): #assume that first non-empty item is the jobid
                if len(items[j]) > 0:
                    p = int(items[j].split('.')[0])
                    if p == jobinfo.jobid:
                        still_running = 1 
                        status = get_status(items)
                        still_running = check_status(status)
                  
                        if len(jobinfo.start_time) == 0 and status == 'r':
                            start_time = time.time()
                        else:
                            start_time = jobinfo.start_time
                        return (still_running, line, start_time, status)
                    break
    line = []
    return (still_running, line, start_time, status)

def get_status(items):
# status = get_status(items)
    status = ''
    num = 0
    for j in range(len(items)):
        if len(items[j]) > 0:
            num += 1
        if num == 10:
            status = items[j]
            break
    return status

def check_status(status):
# ret = check_status(status)
    #if status in ['t', 'Eqw', 'dt', 'dr']:
    if status in ['E', 'C', 'S']:
    	return 0
    else:
        return 1

def rproc_submit_and_wait(jobinfo, finish_frac, jobtimeout):
    # [jobinfo,frac_finished]=rproc_submit_and_wait(jobinfo, finish_frac, jobtimeout) 
      
    num_jobs = 0
    for i in range(len(jobinfo)):
        if jobinfo[i].created == 1:
            num_jobs += 1

    num_finished = 0
    while (num_finished / float(num_jobs) < finish_frac):
        num_finished = 0
        for id in range(len(jobinfo)):
            if rproc_finished(jobinfo[id]): 
                num_finished += 1
            else:
                if jobinfo[id].created == 1:
                    if rproc_time_since_submission(jobinfo[id]) > jobtimeout:
                        print >> sys.stderr, 'WARNING: job took longer than timeout. Killing and restarting it'
                        rproc_kill(jobinfo[id])
                    jobinfo[id] = rproc_resubmit(jobinfo[id], 1)
        print 'waiting for jobs to finish: %i/%i  \r' % (num_finished, num_jobs)
        if (num_finished / float(num_jobs) < finish_frac):
            time.sleep(10)

    print ''

def rproc_submit_batch(jobinfo, blocksize):
    # [jobinfo, meta_jobinfo] = rproc_submit_many(jobinfo, blocksize) 

    meta_jobinfo = rproc_empty(0)

    time_per_submission = 1.0/60 # 1 seconds

    time_per_metajob = [0 for i in range(int(math.ceil(len(jobinfo) / float(blocksize))))]
    metablockassignment = [0 for i in range(len(jobinfo))]
    s_idx = sorted(range(len(jobinfo)), key=(lambda x: -jobinfo[x].time))
    for i in sidx:
        step = (time_per_submission * length(time_per_metajob)) / (len(time_per_metajob) - 1)
        span = [-time_per_submission * len(time_per_metajob) + (ii * step) for ii in range(len(time_per_metajob))]
        span = [span[x] + time_per_metajob[x] for x in range(len(span))]
        idx = span.index(min(span))
        metablockassignment[i] = idx
        time_per_metajob[idx] += jobinfo[i].time

    meta_i = 1
    for i in range(int(math.ceil(len(jobinfo) / float(blocksize)))):
        idx = [ii for ii in range(len(metablockassignment)) if metablockassignment[ii] == i]
        if len(idx) == 0:
            continue
        for j in range(len(idx)):
            options = jobinfo[idx[j]].options
            options.submit_now = 0
            jobinfo[idx[j]] = rproc(jobinfo[idx[j]].ProcName, jobinfo[idx[j]].P1, jobinfo[idx[j]].Mem, options, jobinfo[idx[j]].time, jobinfo[idx[j]].callfile, resubmission=True)
        jobinfo_ = jobinfo[idx]
        options = jobinfo[idx[0]].options
        options.submit_now = 1
        options.verbosity = 1
        memory_MB = max([x.Mem for x in jobinfo_])
        minutes = sum([int(x.time) for x in jobinfo_])
        print 'submitting job %i/%i (%i subjobs) \r' % (i, int(math.ceil(len(jobinfo) / float(blocksize))), len(idx))
        meta_jobinfo[meta_i] = rproc('rproc_submit_batch_helper', jobinfo_, memory_MB, options, minutes)
        
        for j in range(len(idx)):
            jobinfo[idx[j]].log_fname = meta_jobinfo[meta_i].log_fname
            jobinfo[idx[j]].jobid = meta_jobinfo[meta_i].jobid
            jobinfo[idx[j]].submission_time = meta_jobinfo[meta_i].submission_time
        meta_i += 1
    print ''

    return (jobinfo, meta_jobinfo)


def rproc_submit_batch_helper(parameters):
    # x = rproc_submit_batch_helper(parameters)

    print 'Executing a batch of %i jobs in a super-job' % len(parameters) 
    pp = os.getcwd()
    for i in range(len(parameters)):
        os.chdir(pp)
        print 'starting job %i in file %s'  %(i, parameters[i].mat_fname)
        print '========================================='
        try:
            start_proc(parameters[i].mat_fname, 0)
        except:
            print >> sys.stderr, 'execution of start_proc failed'

    # remove files
    for i in range(len(parameters)):
        fname = parameters[i].mat_fname
        os.remove(fname) # mat file
        os.remove('%spy' % fname.strip('pickle')) # m file

    return 0


def rproc_time_since_submission(jobinfo):
    # time = rproc_time_since_submission(jobinfo)
    # returns time in minutes since submission  
    return (time.time() - jobinfo.submission_time)/60 

def rproc_wait(jobinfo, pausetime=120, frac_finished=1.0, resub_on=1, verbosity=2):
    # [jobinfo, num_crashed] = rproc_wait(jobinfo, pausetime, frac_finished, resub_on, verbosity) 

    global rproc_wait_jobinfo
    rproc_wait_jobinfo = jobinfo

    if resub_on == 1:
        print '\n\ncrashed jobs will be resubmitted by rproc_wait'
    elif resub_on == -1:
        print '\n\ncrashed jobs may be resubmitted by rproc_wait'
    else:
        print '\n\ncrashed jobs will not be resubmitted by rproc_wait'

    if not isinstance(jobinfo, list):
        jobinfo = [jobinfo]

    num_jobs = 0
    num_crashed = 0
    for i in range(len(jobinfo)):
        if jobinfo[i].created == 1:
            if jobinfo[i].time is None:
                print >> sys.stderr, 'WARNING: job created but not submitted yet. ignoring'
                jobinfo[i].created = 0
            else:
                num_jobs += 1

    num_finished = 0 
    first_iter = True
    while (num_finished < num_jobs * frac_finished) or (num_crashed > 0):
        if not first_iter:
            time.sleep(pausetime)
        first_iter = False
        num_finished = 0
        num_crashed  = 0
        crashed_files = 'log files of crashed jobs:'
        for id in range(len(jobinfo)):
            cur_finished = rproc_finished(jobinfo[id])
            (still_running, qstat_line, start_time, status) = rproc_still_running(jobinfo[id])
            if status == -1:
                return (jobinfo, num_crashed)

            jobinfo[id].start_time = start_time
            if cur_finished:
                num_finished += 1
            elif not still_running:
                num_finished += 1
                num_crashed += 1
                crashed_files = '%s\n%s' % (crashed_files, jobinfo[id].log_fname)
                if jobinfo[id].crashed_time is None:
                    jobinfo[id].crashed_time = time.time()
                elif 24 * 60 * (time.time() - jobinfo[id].crashed_time) > max(3 * (pausetime/60), 0.1)  and (resub_on == 1 or (resub_on == -1 and jobinfo[id].resubmit >= jobinfo[id].retries + 1)):
                    if resub_on == 1:
                        (reachedlimit, jobwalltime) = rproc_reached_timelimit(jobinfo[id])
                        if reachedlimit: # check whether the job has been killed because it reached the time limit
                            if verbosity >= 1:
                                print 'job has been canceled because it used %1.0fs, but time limit was %1.0fs walltime.\nhence, we increase the time limit to %1.0fs.\n' % (jobwalltime, jobinfo[id].time * 60, max(jobinfo[id].time, jobwalltime) * 2)
                            jobinfo[id].time = max(jobinfo[id].time, jobwalltime / 60) * 2
                    elif resub_on == -1:
                        jobinfo[id].time = jobinfo[id].time_req_resubmit[min(jobinfo[id].retries + 1, len(jobinfo[id].time_req_resubmit) - 1)]
                        jobinfo[id].Mem = jobinfo[id].mem_req_resubmit[min(jobinfo[id].retries + 1, len(jobinfo[id].mem_req_resubmit) - 1)] 
                        jobinfo[id].start_time = []
                        if verbosity >= 1:
                            print 'resubmitting job (%i) with new time and memory limitations: %iMb and %i minutes (retry #%i)\n' % (jobinfo[id].jobid, jobinfo[id].Mem, jobinfo[id].time, jobinfo[id].retries + 1)
                    if verbosity >= 2:
                        print 'log file of previous attempt %s\n' % jobinfo[id].log_fname
                    jobinfo[id] = rproc_resubmit(jobinfo[id]) 
                    jobinfo[id].crashed_time = None 
                    num_finished -= 1
            else:
                if verbosity >= 2:
                    print '%s' % qstat_line
            ### hard_time_limit in minutes
            if len(jobinfo[id].start_time) > 0 and 24 * 60 * (time.time() - jobinfo[id].start_time) > jobinfo[id].hard_time_limit:
                print 'delete job (%i) because hard time limit (%imin) was reached\n' % (jobinfo[id].jobid, jobinfo[id].hard_time_limit)
                subprocess.call(['qdel', str(jobinfo[id].jobid)])
        if verbosity >= 1:
            print '\n%i of %i jobs finished (%i of them crashed) \n' % (num_finished, num_jobs, num_crashed)
        if verbosity >= 2:
            if len(crashed_files.strip().split('\n')) > 0:
                print '%s\n' % crashed_files
        if resub_on == 0 and num_finished == num_jobs * frac_finished:
            break
        if resub_on == -1 and num_finished == num_jobs * frac_finished:
            all_tried = True
            for i in range(len(jobinfo)):
                fin = rproc_finished(jobinfo[i])
                if (jobinfo[i].resubmit >= jobinfo[i].retries + 1) and not fin:
                    all_tried = False
            if all_tried:
                break

    time.sleep(1)

def start_proc(fname, rm_flag=True):
    # start_proc(fname, rm_flag)
      
    global THIS_IS_A_RPROC_PROCESS  
    THIS_IS_A_RPROC_PROCESS = True

    (ProcName, P1, dirctry, options, callfile) = cPickle.load(open(fname, 'r'))
    os.chdir(dirctry)

    print '%s on %s started (in %s; from %s)' % (ProcName, os.environ['HOSTNAME'], dirctry, fname)
    print '### job started %s' % time.strftime('%Y-%m-%d %H:%S')

    if 'rmpaths' in options:
        for i in range(len(options['rmpaths'])):
            print 'removing path %s' % options['rmpaths'][i]
            while options['rmpaths'][i] in sys.path:
                r_idx = sys.path.index(options['rmpaths'][i])
                del sys.path[r_idx]

    if 'addpaths' in options:
        for i in range(len(options['addpaths'])):
            if not options['addpaths'][i] in sys.path:
                print 'adding path %s' % options['addpaths'][i]
                sys.path.append(options['addpaths'][i])

    if 'rm_flag' in options:
        rm_flag = options['rm_flag']

    
    ### create environment
    for mod in options['imports']:
        module = options['imports'][mod]
        if module[1] == 'builtin':
            if imp.is_builtin(module[0]) == 1:
                exec('import %s' % module[0])
        else:
            mod_sl = module[0].split('.')
            subpaths = get_subpaths(os.path.dirname(module[1]).split('/'))
            for m in range(len(mod_sl)):
                exec('exists = \'%s\' in globals().items()' % '.'.join(mod_sl[:m+1]))
                if not exists:
                    try:
                        (f, fn, des) = imp.find_module(mod_sl[m], subpaths)
                        try:
                            exec('%s = imp.load_module(\'%s\', f, fn, des)' % ('.'.join(mod_sl[:m+1]), '.'.join(mod_sl[:m+1])))
                        finally:
                            if f is not None:
                                f.close()
                    except ImportError:
                        print >> sys.stderr, 'Module %s could not be found' % '.'.join(mod_sl[:m+1])
            if mod != module[0]:
                exec('%s = %s' % (mod, module[0]))
                

    retval1 = []
    retval2 = []

    
    try:
        exec('from %s import %s' % (callfile[0], ProcName))

        if len(P1) > 0:
            retval = eval('%s(P1)' % ProcName)
        else:
            retval = eval('%s()' % ProcName)
        if retval is None:
            pass
        elif isinstance(retval, tuple):
            retval1 = retval[0]
            retval2 = retval[1]
        else:
            retval1 = retval

        if not ('no_result_file' in options and options['no_result_file']):
            print 'saving results to %s_result.pickle' % os.path.splitext(fname)[0]
            cPickle.dump((retval1, retval2), open('%s_result.pickle' % os.path.splitext(fname)[0], 'wb'), -1) 
    except (NameError, TypeError) as e:
        print >> sys.stderr, 'execution of %s failed' % ProcName
        print >> sys.stderr, '%s' % str(e)
        global MATLAB_RETURN_VALUE
        MATLAB_RETURN_VALUE = -1
        rm_flag = False
    except RprocRerun as e:
        # if we rerun, then we should not cleanup
        print >> sys.stderr, 'job is marked for rerunning. exiting without finished computations'
    else:
        if rm_flag:
            os.remove(fname) # data file
            os.remove('%ssh' % fname.strip('pickle')) # script file

    print '### job finished %s' % time.strftime('%Y-%m-%d %H:%S')

def split_walltime(time_str):

    factors = [1, 60, 3600, 86400]
    seconds = 0
    sl = time_str.split(':')
    for i, j in enumerate(range(len(sl) - 1, -1, -1)):
        if i < len(factors):
            seconds += (int(sl[i]) * factors[j])
        else:
            print >> sys.stderr, 'WARNING: walltime computation exceeds max value'
    return seconds


def get_subpaths(sl):

    return ['/'.join(sl[:len(sl)-i]) for i in range(len(sl) - 1)]

if __name__ == "__main__":
    
    start_proc(sys.argv[1])
