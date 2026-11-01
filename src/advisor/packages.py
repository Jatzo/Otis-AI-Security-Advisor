"""The packages the corpus covers, named the way OSV.dev names them."""

from typing import NamedTuple


class Package(NamedTuple):
    ecosystem: str  # OSV ecosystem name: PyPI, npm or Maven
    name: str


PACKAGES: tuple[Package, ...] = (
    Package("PyPI", "django"),
    Package("PyPI", "flask"),
    Package("PyPI", "jinja2"),
    Package("PyPI", "requests"),
    Package("PyPI", "urllib3"),
    Package("PyPI", "pillow"),
    Package("PyPI", "pyyaml"),
    Package("PyPI", "cryptography"),
    Package("PyPI", "aiohttp"),
    Package("npm", "lodash"),
    Package("npm", "express"),
    Package("npm", "axios"),
    Package("npm", "jsonwebtoken"),
    Package("npm", "ws"),
    Package("npm", "minimist"),
    # Maven is here because KEV lists almost no npm or PyPI libraries; without these
    # three, "is it being exploited?" would have one yes in the whole corpus.
    Package("Maven", "org.apache.logging.log4j:log4j-core"),
    Package("Maven", "org.springframework:spring-webmvc"),
    Package("Maven", "org.apache.struts:struts2-core"),
)
