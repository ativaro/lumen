"""Lumen Code opens the common server UI in its private native host."""
import argparse
from app import create_app


def main(arguments=None):
    parser=argparse.ArgumentParser(description='Lumen Code')
    selection=parser.add_mutually_exclusive_group()
    selection.add_argument('--entry');selection.add_argument('--ref');selection.add_argument('--save-task')
    args=parser.parse_args(arguments)
    from server_notes_app import run
    from interop_data import Registry
    from server_app_session import SessionError
    activation={'reference':args.ref} if args.ref else {'save_task':args.save_task} if args.save_task else {}
    if args.entry:
        from interop_dialogs import run_job
        from server_notes_app import context
        application=create_app()
        checked=run_job(None,'Lumen Code · Serververbindung wird geprüft …',lambda job:context(job,'code'))
        if checked is None:return 1
        binding=checked[1]
        reference=dict(version=2,app='code',id=args.entry,title='Lumen Code',locator=dict(server=binding.origin,account=binding.account))
        binding.reference_url(reference)
        activation={'reference':Registry().register(reference)}
    else:application=create_app()
    application.removeEventFilter(application)
    return run(application,activation,kind='code')


if __name__=='__main__':raise SystemExit(main())
