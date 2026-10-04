//! No path, password, field, environment or stdin input is supported by this probe.
fn main() {
    if std::env::args_os().len() != 1 {
        eprintln!("This synthetic probe accepts no arguments.");
        std::process::exit(2);
    }
    // SAFETY: pointers refer to live rlimit structs; these calls only reduce this
    // process's privileges/resources. Failure prevents the probe from starting.
    unsafe {
        let core = libc::rlimit {
            rlim_cur: 0,
            rlim_max: 0,
        };
        let memory = libc::rlimit {
            rlim_cur: 512 * 1024 * 1024,
            rlim_max: 512 * 1024 * 1024,
        };
        let cpu = libc::rlimit {
            rlim_cur: 60,
            rlim_max: 60,
        };
        if libc::setrlimit(libc::RLIMIT_CORE, &core) != 0
            || libc::setrlimit(libc::RLIMIT_AS, &memory) != 0
            || libc::setrlimit(libc::RLIMIT_CPU, &cpu) != 0
            || libc::prctl(libc::PR_SET_DUMPABLE, 0) != 0
            || libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0
        {
            eprintln!("Probe hardening failed.");
            std::process::exit(1);
        }
        libc::alarm(90);
    }
    std::panic::set_hook(Box::new(|_| {
        eprintln!("Probe stopped after an internal failure.")
    }));
    match lumen_vault_core::qualify() {
        Ok(checks) => {
            for check in checks {
                println!("{check}");
            }
        }
        Err(error) => {
            eprintln!("Synthetic probe failed: {error:?}");
            std::process::exit(1);
        }
    }
}
