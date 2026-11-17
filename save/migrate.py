"""Save migration and checksum (starter code with known defects)."""


def migrate(save, target_version):
    return dict(save)


def checksum(save):
    return 0


def merge_cloud(local, remote):
    return {"coins": 0, "level": 0, "version": 0}
