from .cli import main
if __name__ == '__main__':
    import sys
    args=['scan']+sys.argv[1:]
    raise SystemExit(main(args))
