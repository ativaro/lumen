//! Private child of the explicitly opted-in laboratory UI; stdin/stdout are IPC.
#[global_allocator]
static ALLOCATOR: lumen_vault_core::memory::WipingAllocator =
    lumen_vault_core::memory::WipingAllocator;
fn main() {
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 3 || args[1] != "--laboratory-only" {
        std::process::exit(2);
    }
    // SAFETY: scalar prctl values and valid rlimit pointers; reduce privileges only.
    unsafe {
        let core = libc::rlimit {
            rlim_cur: 0,
            rlim_max: 0,
        };
        let memory = libc::rlimit {
            rlim_cur: 512 * 1024 * 1024,
            rlim_max: 512 * 1024 * 1024,
        };
        if libc::isatty(0) != 0
            || libc::isatty(1) != 0
            || libc::setrlimit(libc::RLIMIT_CORE, &core) != 0
            || libc::setrlimit(libc::RLIMIT_AS, &memory) != 0
            || libc::prctl(libc::PR_SET_DUMPABLE, 0) != 0
            || libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
            || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM) != 0
        {
            std::process::exit(1);
        }
        if libc::getppid() == 1 {
            std::process::exit(1);
        }
    }
    std::panic::set_hook(Box::new(|_| {}));
    if lumen_vault_core::laboratory::serve(std::path::Path::new(&args[2])).is_err() {
        std::process::exit(1);
    }
}
