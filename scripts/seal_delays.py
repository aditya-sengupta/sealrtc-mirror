import numpy as np
from matplotlib import pyplot as plt
import sys
import re
from os.path import join

from sealrtc.constants import fs
from sealrtc import loadres

# res = loadres(join("lqg", "klqg_nstate_20_amp_0.005_ang_0.7853981633974483_f_1_tstamp_2021_11_17_17_31_28.csv"))
from kfvib import run
res = run()

get_meanstd = lambda data: f"{round(np.mean(data), 3)} $\pm$ {round(np.std(data), 3)}"
measure_delays = (res.tmeas - res.texp) * fs
control_delays = (res.tdmc - res.tmeas) * fs
total_delays = (res.tdmc - res.texp) * fs

fig, axs = plt.subplots(1,3, figsize=(12,8))
def plot_delay_hist(data, i, xlabel, title):
    bins = int(max(data) * 1000 / fs) + 1
    axs[i].hist(data, bins=min(100, bins), range = (0, min(5, max(total_delays))))
    axs[i].set_xlabel(xlabel)
    axs[i].set_ylabel("Count")
    axs[i].set_title(f"{title}: {get_meanstd(data)} frames")

for (i, (data, xlabel, title)) in enumerate([
    (total_delays, "Exposure to DM command", "Overall AO loop"),
    (measure_delays, "Measurement to DM command", "Measurement"),
    (control_delays, "Exposure to measurement", "Controller")
]):
    plot_delay_hist(data, i, xlabel, title)
fig.suptitle("Delays in the AO loop on SEAL, in #frames")
plt.show()
#plt.savefig("../plots/seal_delay.pdf")