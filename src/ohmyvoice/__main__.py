import sys


def main():
    if "--worker" in sys.argv:
        from ohmyvoice.worker import main as worker_main
        worker_main()
    else:
        from ohmyvoice.app import main as app_main
        app_main()


main()
