"""La passerelle répond-elle vraiment ? Sort 0 si oui, 1 sinon. Lecture seule, client 98."""
import sys

from ib_insync import IB


def main(port: int) -> int:
    ib = IB()
    try:
        ib.connect("127.0.0.1", port, clientId=98, timeout=15, readonly=True)
        return 0
    except Exception:
        return 1
    finally:
        ib.disconnect()


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1])))
