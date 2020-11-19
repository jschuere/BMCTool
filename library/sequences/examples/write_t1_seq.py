"""
Script to output a seq file for a WASABI protocol for simultaneous mapping of B0 and B1 according to:
Schuenke et al. Simultaneous mapping of water shift and B1 (WASABI)-Application to field-Inhomogeneity correction of
CEST MRI data. Magnetic Resonance in Medicine, 77(2), 571–580. https://doi.org/10.1002/mrm.26133
parameter settings:
     pulse shape = block
     B1 = 3.75 uT (@ 3T; in general 1.25 uT multiplied by field strength)
     n = 1
     t_p = 5 ms (@ 3T; in general 15 ms devided by field strength)
     T_rec = 2/12 s (saturated/M0)
"""

import numpy as np

from pypulseq.Sequence.sequence import Sequence
from pypulseq.make_adc import make_adc
from pypulseq.make_delay import make_delay
from pypulseq.make_trap_pulse import make_trapezoid
from pypulseq.make_block_pulse import make_block_pulse
from pypulseq.make_sinc_pulse import make_sinc_pulse
from pypulseq.make_gauss_pulse import make_gauss_pulse
from pypulseq.opts import Opts
from sim.utils.seq.conversion import convert_seq_12_to_pseudo_13

seq = Sequence()

offset_range = 2  # [ppm]
num_offsets = 21  # number of measurements (not including M0)
run_m0_scan = True  # if you want an M0 scan at the beginning
t_rec = 2  # recovery time between scans [s]
m0_t_rec = 12  # recovery time before m0 scan [s]
sat_b1 = 3.75  # mean sat pulse b1 [uT]
t_p = 5e-3  # sat pulse duration [s]
t_d = 0  # delay between pulses [s]
n_pulses = 1  # number of sat pulses per measurement
b0 = 3  # B0 [T]
spoiling = 1  # 0=no spoiling, 1=before readout, Gradient in x,y,z
spoil_delay = 1e-3

seq_filename = 'external.seq'  # filename

# scanner limits
sys = Opts(max_grad=40, grad_unit='mT/m', max_slew=130, slew_unit='T/m/s', rf_ringdown_time=30e-6, rf_dead_time=100e-6,
           rf_raster_time=1e-6)
gamma = sys.gamma * 1e-6

# scanner events
# sat pulse
flip_angle_sat = sat_b1 * gamma * 2 * np.pi * t_p  # rad
rf_sat, _ = make_block_pulse(flip_angle=flip_angle_sat, duration=t_p, system=sys)

# spoilers
spoil_amp = 0.8 * sys.max_grad  # Hz/m
spoil_amp1 = -0.7 * sys.max_grad  # Hz/m
spoil_amp2 = 0.6 * sys.max_grad  # Hz/m
spoil_dur = 5500e-6  # s
gx_spoil, gy_spoil, gz_spoil = [make_trapezoid(channel=c, system=sys, amplitude=spoil_amp, duration=spoil_dur,
                                               rise_time=1000e-6) for c in ['x', 'y', 'z']]
gx_spoil1, gy_spoil1, gz_spoil1 = [make_trapezoid(channel=c, system=sys, amplitude=spoil_amp1, duration=spoil_dur,
                                               rise_time=1000e-6) for c in ['x', 'y', 'z']]
gx_spoil2, gy_spoil2, gz_spoil2 = [make_trapezoid(channel=c, system=sys, amplitude=spoil_amp2, duration=spoil_dur,
                                               rise_time=1000e-6) for c in ['x', 'y', 'z']]

# 90 degree pulse
flip_angle_t1 = (90 * 2 * np.pi)/180
t1_dur = 2.5e-3
t1_rf, _, _ = make_sinc_pulse(flip_angle=flip_angle_t1, duration=t1_dur, system=sys, time_bw_product=3)
# rf_ex, gz, _ = make_sinc_pulse(flip_angle=flip_ex, system=system, duration=t_ex, slice_thickness=slice_thickness,
                               # apodization=0.5, time_bw_product=4, phase_offset=rf_ex_phase)

# pseudo adc (not played out)
pseudo_adc = make_adc(num_samples=1, duration=1e-3)

# loop through z spectrum offsets
offsets_ppm = np.linspace(-offset_range, offset_range, num_offsets)
offsets = offsets_ppm * gamma * b0

if run_m0_scan:
    seq.add_block(make_delay(m0_t_rec))
    seq.add_block(pseudo_adc)

# loop through offsets and set pulses and delays
for o in offsets:
    seq.add_block(make_delay(1e-6))
    for i in range(6):
        seq.add_block(t1_rf)
        seq.add_block(make_delay(spoil_delay))
        if i % 3 == 0:
            seq.add_block(gx_spoil, gy_spoil1, gz_spoil2)
        elif i % 2 == 0:
            seq.add_block(gx_spoil2, gy_spoil, gz_spoil1)
        else:
            seq.add_block(gx_spoil1, gy_spoil2, gz_spoil)
        seq.add_block(make_delay(spoil_delay))
    # take care of phase accumulation during off-res pulse
    accum_phase = 0
    seq.add_block(make_delay(t_rec))  # recovery time
    rf_sat.freq_offset = o
    for n in range(n_pulses):
        rf_sat.phase_offset = accum_phase
        seq.add_block(rf_sat)
        accum_phase = np.mod(accum_phase + o * 2 * np.pi * np.where(np.abs(rf_sat.signal) > 0)[0].size * 1e-6, 2 * np.pi)
        if n < n_pulses-1:
            seq.add_block(make_delay(t_d))
    print(np.where(offsets == o)[0][0], '/', len(offsets), ': offset ', o)
    if spoiling:
        seq.add_block(make_delay(spoil_delay))
        seq.add_block(gx_spoil, gy_spoil, gz_spoil)
        seq.add_block(make_delay(spoil_delay))
    seq.add_block(pseudo_adc)

seq.set_definition('offsets_ppm', offsets_ppm)
seq.set_definition('run_m0_scan', str(run_m0_scan))

# plot the sequence
# seq.plot()
print(seq.shape_library)
seq.write(seq_filename)
# convert to pseudo version 1.3
convert_seq_12_to_pseudo_13(seq_filename)
