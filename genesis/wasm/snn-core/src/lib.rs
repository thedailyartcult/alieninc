//! Genesis Core — LIF SNN simulator compiled to WebAssembly.
//!
//! Implements:
//!   tau_m * (dV_i/dt) = -(V_i - V_rest) + R * sum_j W_ij S_j(t)
//!
//! Exposes a flat C ABI that the JS terminal drives through the raw
//! WebAssembly memory API (no wasm-bindgen required).

const TAU_M: f32 = 10.0;
const V_REST: f32 = -70.0;
const V_THRESH: f32 = -55.0;
const V_RESET: f32 = -75.0;
const R_M: f32 = 1.0;
const DT: f32 = 1.0;

// Deterministic PRNG (xorshift) so simulations are reproducible in-browser.
struct Rng(u32);
impl Rng {
    fn next(&mut self) -> u32 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        self.0 = x;
        x
    }
    fn chance(&mut self, n: u32, d: u32) -> bool {
        (self.next() % d) < n
    }
}

// --- Module-level simulation state ---
// All arrays live in Wasm linear memory so JS can pass pointers.
static mut N: usize = 0;
static mut N_EDGES: usize = 0;
static mut N_STEPS: usize = 0;
static mut V: *mut f32 = core::ptr::null_mut();
static mut PRE: *mut u32 = core::ptr::null_mut();
static mut POST: *mut u32 = core::ptr::null_mut();
static mut W: *mut f32 = core::ptr::null_mut();
static mut SYNAPSE_IN: *mut f32 = core::ptr::null_mut();
static mut SPIKES: *mut u32 = core::ptr::null_mut();
static mut SPIKE_RASTER: *mut u32 = core::ptr::null_mut();
static mut RASTER_COUNT: *mut u32 = core::ptr::null_mut();

/// init(n, n_edges, n_steps, budgets...) — allocate buffers.
///
/// JS must allocate the following lengths (f32/u32 words):
///   V      : n
///   PRE    : n_edges
///   POST   : n_edges
///   W      : n_edges
///   SYNAPSE_IN : n
///   SPIKES : n
///   SPIKE_RASTER : n_steps * n  (spike bitmask footprint, capped)
///   RASTER_COUNT : n_steps
#[no_mangle]
pub extern "C" fn snn_init(n: u32, n_edges: u32, n_steps: u32,
                           v_ptr: u32, pre_ptr: u32, post_ptr: u32, w_ptr: u32,
                           syn_ptr: u32, spikes_ptr: u32,
                           raster_ptr: u32, raster_count_ptr: u32) {
    unsafe {
        N = n as usize;
        N_EDGES = n_edges as usize;
        N_STEPS = n_steps as usize;
        V = v_ptr as *mut f32;
        PRE = pre_ptr as *mut u32;
        POST = post_ptr as *mut u32;
        W = w_ptr as *mut f32;
        SYNAPSE_IN = syn_ptr as *mut f32;
        SPIKES = spikes_ptr as *mut u32;
        SPIKE_RASTER = raster_ptr as *mut u32;
        RASTER_COUNT = raster_count_ptr as *mut u32;

        for i in 0..N {
            *V.add(i) = V_REST;
            *SPIKES.add(i) = 0;
        }
        for i in 0..n_spike_total() {
            *SPIKE_RASTER.add(i) = 0;
        }
        for t in 0..N_STEPS {
            *RASTER_COUNT.add(t) = 0;
        }
    }
}

#[inline]
fn n_max() -> usize { unsafe { N } }
#[inline]
fn n_edges() -> usize { unsafe { N_EDGES } }
#[inline]
fn n_steps() -> usize { unsafe { N_STEPS } }
#[inline]
fn n_spike_words() -> usize { unsafe { (N + 31) / 32 } }

fn n_spike_total() -> usize { unsafe { N_STEPS * ((N + 31) / 32) } }

/// Load one edge-set into the PRE/POST/W arrays (edges are placed by JS
/// directly in linear memory; this marks the base offsets for clarity).
#[no_mangle]
pub extern "C" fn snn_set_edges(_start: u32, _count: u32) {
}

/// Run the simulation. Returns total spikes (u32).
#[no_mangle]
pub extern "C" fn snn_run(seed: u32) -> u32 {
    unsafe {
        let n = n_max();
        let mut rng = Rng(seed | 1);
        let mut total_spikes: u32 = 0;

        for t in 0..n_steps() {
            // zero synaptic input
            for i in 0..n {
                *SYNAPSE_IN.add(i) = 0.0;
            }

            // add weights from firing pre-synaptic neurons
            for e in 0..n_edges() {
                let pre = *PRE.add(e) as usize;
                if pre < n && *SPIKES.add(pre) != 0 {
                    let post = *POST.add(e) as usize;
                    if post < n {
                        *SYNAPSE_IN.add(post) += *W.add(e);
                    }
                }
            }

            // LIF update + Poisson noise + threshold
            let mut step_count: u32 = 0;
            let word = t * n_spike_words();
            for i in 0..n {
                let mut v = *V.add(i);
                let i_syn = *SYNAPSE_IN.add(i);

                v += (DT / TAU_M) * (-(v - V_REST) + R_M * i_syn);

                // Poisson input
                if rng.chance(4, 1000) {
                    v += 14.0;
                }

                let fired = v >= V_THRESH;
                *SPIKES.add(i) = if fired { 1 } else { 0 };
                if fired {
                    v = V_RESET;
                    step_count += 1;
                    // set bit in raster
                    let bit = i & 31;
                    // SPIKE_RASTER[word + i/32]
                    *SPIKE_RASTER.add(word + (i >> 5)) |= 1u32 << bit;
                }
                *V.add(i) = v;
            }

            *RASTER_COUNT.add(t) = step_count;
            total_spikes += step_count;
        }

        total_spikes
    }
}

/// Compute mean firing rate in Hz over the whole run.
#[no_mangle]
pub extern "C" fn snn_mean_rate(total_spikes: u32) -> f32 {
    unsafe {
        let sim_ms = N_STEPS as f32 * DT;
        let sim_s = sim_ms / 1000.0;
        if sim_s <= 0.0 || N == 0 {
            return 0.0;
        }
        total_spikes as f32 / sim_s / N as f32
    }
}

/// Helper: get total raster words allocated.
#[no_mangle]
pub extern "C" fn snn_raster_words() -> u32 {
    ((n_max() + 31) / 32) as u32
}
