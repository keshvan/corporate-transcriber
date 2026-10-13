class MediaError(Exception):
    pass

class InvalidMediaError(MediaError):
    pass

class MediaToolError(MediaError):
    pass
