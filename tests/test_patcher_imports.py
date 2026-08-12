"""The texture encoder must not drag FMOD in with it.

UnityPy.export imports its audio converter, which loads a native FMOD library
the frozen builds do not ship. Importing patcher has to make that harmless.
"""
import sys


def test_texture_encoder_imports_without_fmod():
    import patcher  # noqa: F401 — the import itself is what is under test

    assert not hasattr(sys.modules["fmod_toolkit"], "raw_to_wav"), \
        "the real fmod_toolkit got imported — the stub went in too late"
    from UnityPy.export.Texture2DConverter import image_to_texture2d
    assert callable(image_to_texture2d)
