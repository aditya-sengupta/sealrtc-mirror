# authored by Aditya Sengupta

import time
import os
import numpy as np
import warnings
from datetime import datetime
from threading import Thread
from queue import Queue
from functools import partial

from ..constants import dt
from ..utils import joindata
from ..optics import optics
from ..optics import measure_zcoeffs, make_im_cm
from ..optics import align

bestflat = np.load(joindata("bestflats/bestflat.npy"))

def record_im(out_q, t=1, timestamp=datetime.now().strftime("%d_%m_%Y_%H_%M_%S")):
    t1 = time.time()
    times = [] 

    while time.time() < t1 + t:
        imval = optics.getim()
        times.append(time.time())
        out_q.put(imval)

    out_q.put(None) 
    # this is a placeholder to tell the queue that there's no more images coming
    
    times = np.array(times) - t1
    fname = joindata("recordings/rectime_stamp_{0}.npy".format(timestamp))
    np.save(fname, times)
    return times
    
def tt_from_queued_image(in_q, out_q, cmd_mtx, timestamp=datetime.now().strftime("%d_%m_%Y_%H_%M_%S")):
    imflat = np.load(joindata("bestflats/imflat.npy"))
    fname = joindata("recordings/rectt_stamp_{0}.npy".format(timestamp))
    ttvals = []
    while True:
        # if you don't have any work, take a nap!
        if in_q.empty():
            time.sleep(dt)
        else:
            v = in_q.get()
            in_q.task_done()
            if v is not None:
                ttval = measure_zcoeffs(v - imflat, cmd_mtx=cmd_mtx).flatten()
                out_q.put(ttval)
                ttvals.append(ttval)
            else:
                ttvals = np.array(ttvals)
                np.save(fname, ttvals)
                return ttvals

def control_schedule(q, control, t=1):
    """
    The SEAL schedule for a controller.

    Arguments
    ---------
    q : Queue
    The queue to poll for new tip-tilt values.

    control : callable
    The function to execute control.
    """
    last_tt = None # the most recently applied control command
    t1 = time.time()
    while time.time() < t1 + t:
        if q.empty():
            time.sleep(dt/2)
        else:
            tt = q.get()
            q.task_done()
            last_tt, dmcmd = control(tt, u=last_tt)
            optics.applydmc(dmcmd)

def record_experiment(path, control_schedule, dist_schedule, t=1, verbose=True):
    _, cmd_mtx = make_im_cm(verbose)
    bestflat, imflat = optics.refresh(verbose)
    optics.applydmc(bestflat)
    baseline_ttvals = measure_tt(optics.getim() - imflat, cmd_mtx=cmd_mtx)

    i = 0
    imax = 10
    while np.any(np.abs(baseline_ttvals) > 0.03):
        warnings.warn("The system may not be aligned: baseline TT is {}".format(baseline_ttvals.flatten()))
        align_fast2(view=False)
        _, cmd_mtx = make_im_cm()
        bestflat, imflat = optics.refresh()
        optics.applydmc(bestflat)
        baseline_ttvals = measure_tt(optics.getim() - imflat, cmd_mtx=cmd_mtx)
        i += 1
        if i > imax:
            print("Cannot align system: realign manually and try experiment again.")
            return [], []
    

    timestamp = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")
    path = joindata(path) + "_time_stamp_" + timestamp + ".npy"

    q_compute = Queue()
    q_control = Queue()
    record_thread = Thread(target=partial(record_im, t=t, timestamp=timestamp), args=(q_compute,))
    compute_thread = Thread(target=partial(tt_from_queued_image, timestamp=timestamp), args=(q_compute, q_control, cmd_mtx,))
    control_thread = Thread(target=partial(control_schedule, t=t), args=(q_control,))
    command_thread = Thread(target=dist_schedule)

    if verbose:
        print("Starting recording and commands...")

    record_thread.start()
    compute_thread.start()
    control_thread.start()
    command_thread.start()

    q_compute.join()
    q_control.join()
    record_thread.join(t)
    compute_thread.join(t)
    control_thread.join(t)
    command_thread.join(t)

    if verbose:
        print("Done with experiment.")

    optics.applydmc(bestflat)

    timepath = joindata("recordings/rectime_stamp_{0}.npy".format(timestamp))
    ttpath = joindata("recordings/rectt_stamp_{0}.npy".format(timestamp))
    times = np.load(timepath)
    ttvals = np.load(ttpath)
    np.save(path, times)
    path = path.replace("time", "tt")
    np.save(path, ttvals)
    os.remove(timepath)
    os.remove(ttpath)
    return times, ttvals 
