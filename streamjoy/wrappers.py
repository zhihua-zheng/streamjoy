from __future__ import annotations

import os
from functools import wraps
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from . import _utils
from .models import Paused
from .settings import config


def wrap_matplotlib(
    in_memory: bool = False,
    scratch_dir: str | Path | None = None,
    fsspec_fs: Any | None = None,
) -> Callable:
    """
    Wraps a function used to render a matplotlib figure so that
    it automatically saves the figure and closes it.

    Args:
        in_memory: Whether to render the figure in-memory.
        scratch_dir: The scratch directory to use.
        fsspec_fs: The fsspec filesystem to use.

    Returns:
        The wrapped function.
    """

    def wrapper(renderer):
        @wraps(renderer)
        def wrapped(*args, **kwargs) -> Path | BytesIO:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            plt.rcParams.update({"figure.max_open_warning": config["max_open_warning"]})

            output = renderer(*args, **kwargs)

            fig = output
            return_paused = False
            if isinstance(output, Paused):
                return_paused = True
                fig = output.output

            if isinstance(fig, plt.Axes):
                fig = fig.figure
            elif not isinstance(fig, plt.Figure):
                raise ValueError("Renderer must return a Figure or Axes object.")

            uri = _utils.resolve_uri(
                file_name=f"{hash(fig)}.jpg",
                scratch_dir=scratch_dir,
                in_memory=in_memory,
                fsspec_fs=fsspec_fs,
            )
            if fsspec_fs:
                with fsspec_fs.open(uri, "wb") as f:
                    buf = BytesIO()
                    fig.savefig(buf, format="jpg")
                    buf.seek(0)
                    f.write(buf.read())
            else:
                fig.savefig(uri, format="jpg")
            plt.close(fig)
            return (
                uri if not return_paused else Paused(output=uri, seconds=output.seconds)
            )

        return wrapped

    return wrapper


def wrap_holoviews(
    in_memory: bool = False,
    scratch_dir: str | Path | None = None,
    fsspec_fs: Any | None = None,
    webdriver: str | Callable | None = None,
) -> Callable:
    """
    Wraps a function used to render a holoviews object so that
    it automatically saves the object.

    Args:
        in_memory: Whether to render the object in-memory.
        scratch_dir: The scratch directory to use.
        fsspec_fs: The fsspec filesystem to use.

    Returns:
        The wrapped function.
    """
    if in_memory:
        raise ValueError("Holoviews renderer does not support in-memory rendering.")

    def wrapper(renderer):
        @wraps(renderer)
        def wrapped(*args, **kwargs) -> Path | BytesIO:
            import holoviews as hv

            backend = kwargs.get("backend", hv.Store.current_backend)
            output = renderer(*args, **kwargs)

            hv_obj = output
            return_paused = False
            if isinstance(output, Paused):
                return_paused = True
                hv_obj = output.output

            uri = _utils.resolve_uri(
                file_name=f"{hash(hv_obj)}.png",
                scratch_dir=scratch_dir,
                in_memory=in_memory,
                fsspec_fs=fsspec_fs,
            )
            uri_dir = os.path.dirname(uri)
            if backend == "bokeh":
                from bokeh.io.export import get_screenshot_as_png

                with _utils.get_webdriver(webdriver) as driver:
                    image = get_screenshot_as_png(
                        hv.render(hv_obj, backend=backend), driver=driver
                    )
                    if fsspec_fs:
                        with fsspec_fs.open(uri, "wb") as f:
                            image.save(f)
                    else:
                        image.save(uri)
            else:
                if fsspec_fs:
                    with fsspec_fs.open(uri, "wb") as f:
                        buf = BytesIO()
                        hv.save(hv_obj, buf, fmt="png")
                        buf.seek(0)
                        f.write(buf.read())
                else:
                    hv.save(hv_obj, uri, fmt="png", backend=backend)

            return (
                uri if not return_paused else Paused(output=uri, seconds=output.seconds)
            )

        return wrapped

    return wrapper
