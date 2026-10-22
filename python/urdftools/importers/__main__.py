"""Desktop trusted-main bridge. No arbitrary filesystem path HTTP endpoint."""
import json
import sys
from .service import ImportService


def main():
    request = json.load(sys.stdin)
    service = ImportService(sys.argv[1])
    if request['action'] == 'import':
        report = service.ingest(request['source'])
    elif request['action'] == 'select':
        report = service.select(request['operation_id'], request['model'])
    else:
        raise ValueError('Unknown import action')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
