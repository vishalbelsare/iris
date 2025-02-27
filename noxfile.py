"""
Perform test automation with nox.

For further details, see https://nox.thea.codes/en/stable/#

"""

import hashlib
import os
from pathlib import Path

import nox
from nox.logger import logger

#: Default to reusing any pre-existing nox environments.
nox.options.reuse_existing_virtualenvs = True

#: Name of the package to test.
PACKAGE = str("lib" / Path("iris"))

#: Cirrus-CI environment variable hook.
PY_VER = os.environ.get("PY_VER", ["3.7", "3.8"])

#: Default cartopy cache directory.
CARTOPY_CACHE_DIR = os.environ.get("HOME") / Path(".local/share/cartopy")


def session_lockfile(session: nox.sessions.Session) -> Path:
    """Return the path of the session lockfile."""
    return Path(
        f"requirements/ci/nox.lock/py{session.python.replace('.', '')}-linux-64.lock"
    )


def session_cachefile(session: nox.sessions.Session) -> Path:
    """Returns the path of the session lockfile cache."""
    lockfile = session_lockfile(session)
    tmp_dir = Path(session.create_tmp())
    cache = tmp_dir / lockfile.name
    return cache


def venv_populated(session: nox.sessions.Session) -> bool:
    """Returns True if the conda venv has been created
    and the list of packages in the lockfile installed."""
    return session_cachefile(session).is_file()


def venv_changed(session: nox.sessions.Session) -> bool:
    """Returns True if the installed session is different to that specified
    in the lockfile."""
    changed = False
    cache = session_cachefile(session)
    lockfile = session_lockfile(session)
    if cache.is_file():
        with open(lockfile, "rb") as fi:
            expected = hashlib.sha256(fi.read()).hexdigest()
        with open(cache, "r") as fi:
            actual = fi.read()
        changed = actual != expected
    return changed


def cache_venv(session: nox.sessions.Session) -> None:
    """
    Cache the nox session environment.

    This consists of saving a hexdigest (sha256) of the associated
    conda lock file.

    Parameters
    ----------
    session: object
        A `nox.sessions.Session` object.

    """
    lockfile = session_lockfile(session)
    cache = session_cachefile(session)
    with open(lockfile, "rb") as fi:
        hexdigest = hashlib.sha256(fi.read()).hexdigest()
    with open(cache, "w") as fo:
        fo.write(hexdigest)


def cache_cartopy(session: nox.sessions.Session) -> None:
    """
    Determine whether to cache the cartopy natural earth shapefiles.

    Parameters
    ----------
    session: object
        A `nox.sessions.Session` object.

    """
    if not CARTOPY_CACHE_DIR.is_dir():
        session.run(
            "python",
            "-c",
            "import cartopy; cartopy.io.shapereader.natural_earth()",
        )


def prepare_venv(session: nox.sessions.Session) -> None:
    """
    Create and cache the nox session conda environment, and additionally
    provide conda environment package details and info.

    Note that, iris is installed into the environment using pip.

    Parameters
    ----------
    session: object
        A `nox.sessions.Session` object.

    Notes
    -----
    See
      - https://github.com/theacodes/nox/issues/346
      - https://github.com/theacodes/nox/issues/260

    """
    lockfile = session_lockfile(session)
    venv_dir = session.virtualenv.location_name

    if not venv_populated(session):
        # environment has been created but packages not yet installed
        # populate the environment from the lockfile
        logger.debug(f"Populating conda env at {venv_dir}")
        session.conda_install("--file", str(lockfile))
        cache_venv(session)

    elif venv_changed(session):
        # destroy the environment and rebuild it
        logger.debug(f"Lockfile changed. Re-creating conda env at {venv_dir}")
        _re_orig = session.virtualenv.reuse_existing
        session.virtualenv.reuse_existing = False
        session.virtualenv.create()
        session.conda_install("--file", str(lockfile))
        session.virtualenv.reuse_existing = _re_orig
        cache_venv(session)

    logger.debug(f"Environment {venv_dir} is up to date")

    cache_cartopy(session)

    # Determine whether verbose diagnostics have been requested
    # from the command line.
    verbose = "-v" in session.posargs or "--verbose" in session.posargs

    if verbose:
        session.run("conda", "info")
        session.run("conda", "list", f"--prefix={venv_dir}")
        session.run(
            "conda",
            "list",
            f"--prefix={venv_dir}",
            "--explicit",
        )


@nox.session
def flake8(session: nox.sessions.Session):
    """
    Perform flake8 linting of iris.

    Parameters
    ----------
    session: object
        A `nox.sessions.Session` object.

    """
    # Pip install the session requirements.
    session.install("flake8")
    # Execute the flake8 linter on the package.
    session.run("flake8", PACKAGE)
    # Execute the flake8 linter on this file.
    session.run("flake8", __file__)


@nox.session
def black(session: nox.sessions.Session):
    """
    Perform black format checking of iris.

    Parameters
    ----------
    session: object
        A `nox.sessions.Session` object.

    """
    # Pip install the session requirements.
    session.install("black==21.5b2")
    # Execute the black format checker on the package.
    session.run("black", "--check", PACKAGE)
    # Execute the black format checker on this file.
    session.run("black", "--check", __file__)


@nox.session
def isort(session: nox.sessions.Session):
    """
    Perform isort import checking of iris codebase.

    Parameters
    ----------
    session: object
        A `nox.sessions.Session` object.

    """
    # Pip install the session requirements.
    session.install("isort")
    # Execute the isort import checker.
    session.run("isort", "--check", ".")


@nox.session(python=PY_VER, venv_backend="conda")
def tests(session: nox.sessions.Session):
    """
    Perform iris system, integration and unit tests.

    Parameters
    ----------
    session: object
        A `nox.sessions.Session` object.

    """
    prepare_venv(session)
    session.install("--no-deps", "--editable", ".")
    session.run(
        "python",
        "-m",
        "iris.tests.runner",
        "--default-tests",
        "--system-tests",
    )


@nox.session(python=PY_VER, venv_backend="conda")
def gallery(session: nox.sessions.Session):
    """
    Perform iris gallery doc-tests.

    Parameters
    ----------
    session: object
        A `nox.sessions.Session` object.

    """
    prepare_venv(session)
    session.install("--no-deps", "--editable", ".")
    session.run(
        "python",
        "-m",
        "iris.tests.runner",
        "--gallery-tests",
    )


@nox.session(python=PY_VER, venv_backend="conda")
def doctest(session: nox.sessions.Session):
    """
    Perform iris doc-tests.

    Parameters
    ----------
    session: object
        A `nox.sessions.Session` object.

    """
    prepare_venv(session)
    session.install("--no-deps", "--editable", ".")
    session.cd("docs")
    session.run(
        "make",
        "clean",
        "html",
        external=True,
    )
    session.run(
        "make",
        "doctest",
        external=True,
    )


@nox.session(python=PY_VER, venv_backend="conda")
def linkcheck(session: nox.sessions.Session):
    """
    Perform iris doc link check.

    Parameters
    ----------
    session: object
        A `nox.sessions.Session` object.

    """
    prepare_venv(session)
    session.install("--no-deps", "--editable", ".")
    session.cd("docs")
    session.run(
        "make",
        "clean",
        "html",
        external=True,
    )
    session.run(
        "make",
        "linkcheck",
        external=True,
    )
