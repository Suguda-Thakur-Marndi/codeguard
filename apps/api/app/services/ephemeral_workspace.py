"""Ephemeral workspace management and safe archive extraction for CodeGuard."""

import os
import shutil
import tarfile
import tempfile
from typing import Any

from app.core.exceptions import CodeGuardException
from app.core.logging import logger


class SecurityArchiveError(CodeGuardException):
    """Raised when an archive contains potentially malicious paths, traversal attempts, or device files."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="SECURITY_ARCHIVE_VIOLATION",
            status_code=400,
            details=details,
        )


class ResourceExhaustionError(CodeGuardException):
    """Raised when an archive exceeds safe resource allocation limits."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="RESOURCE_EXHAUSTION",
            status_code=413,
            details=details,
        )


class EphemeralWorkspace:
    """
    Manages an isolated temporary directory for repository source extraction and AST analysis.

    Guarantees:
    - Path traversal prevention: Rejects absolute paths, Windows drive letters, and '..' escapes.
    - Symlink safety: Rejects symlinks pointing outside the workspace boundary.
    - Device safety: Rejects FIFO, socket, block, and character device entries.
    - Resource bounds: Enforces limits on total extracted bytes, file counts, and single file sizes.
    - Guaranteed cleanup: Ensures complete removal of temporary directories on success or failure.
    """

    MAX_UNCOMPRESSED_BYTES: int = 150 * 1024 * 1024  # 150 MB
    MAX_FILE_COUNT: int = 10_000
    MAX_SINGLE_FILE_BYTES: int = 25 * 1024 * 1024     # 25 MB

    def __init__(self, prefix: str = "codeguard_repo_") -> None:
        self.temp_dir: str = tempfile.mkdtemp(prefix=prefix)
        self.repo_dir: str = self.temp_dir
        self._cleaned: bool = False

    def __enter__(self) -> "EphemeralWorkspace":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        """Safely remove the temporary directory and all extracted files."""
        if not self._cleaned and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Failed to remove ephemeral workspace {self.temp_dir}: {e}")
            self._cleaned = True

    def extract_tarball(self, tarball_bytes: bytes) -> str:
        """
        Safely extract a .tar.gz archive into the ephemeral workspace.

        Returns:
            str: The resolved repository root directory.
        """
        import io

        if not tarball_bytes:
            raise SecurityArchiveError("Cannot extract empty repository archive")

        total_extracted_bytes = 0
        file_count = 0
        base_dir = os.path.abspath(self.temp_dir)

        try:
            with tarfile.open(fileobj=io.BytesIO(tarball_bytes), mode="r:*") as tar:
                members = tar.getmembers()

                # 1. Pre-validation of all members before extracting any file
                for member in members:
                    file_count += 1
                    if file_count > self.MAX_FILE_COUNT:
                        raise ResourceExhaustionError(
                            f"Archive contains too many files ({file_count} > {self.MAX_FILE_COUNT})"
                        )

                    if member.size > self.MAX_SINGLE_FILE_BYTES:
                        raise ResourceExhaustionError(
                            f"File '{member.name}' size ({member.size} bytes) exceeds limit of {self.MAX_SINGLE_FILE_BYTES} bytes"
                        )

                    total_extracted_bytes += member.size
                    if total_extracted_bytes > self.MAX_UNCOMPRESSED_BYTES:
                        raise ResourceExhaustionError(
                            f"Archive total uncompressed size ({total_extracted_bytes} bytes) exceeds limit of {self.MAX_UNCOMPRESSED_BYTES} bytes"
                        )

                    # Reject special/device files
                    if member.isdev() or member.ischr() or member.isblk() or member.isfifo():
                        raise SecurityArchiveError(
                            f"Archive contains forbidden device/FIFO file: '{member.name}'"
                        )

                    # Check path traversal
                    name = member.name
                    if os.path.isabs(name) or (len(name) > 1 and name[1] == ":"):
                        raise SecurityArchiveError(f"Path traversal detected in archive: absolute path '{name}'")

                    # Normalize target path
                    target_path = os.path.normpath(os.path.join(base_dir, name))
                    if not (target_path == base_dir or target_path.startswith(base_dir + os.sep)):
                        raise SecurityArchiveError(
                            f"Path traversal detected in archive: '{name}' escapes base directory"
                        )

                    # Check symlinks / hardlinks
                    if member.issym() or member.islnk():
                        link_target = os.path.normpath(os.path.join(os.path.dirname(target_path), member.linkname))
                        if not (link_target == base_dir or link_target.startswith(base_dir + os.sep)):
                            raise SecurityArchiveError(
                                f"Insecure link in archive: '{member.name}' -> '{member.linkname}' points outside workspace"
                            )

                # 2. Extract verified members
                tar.extractall(path=base_dir)

            # 3. Locate repository root (GitHub tarballs typically have top-level directory owner-repo-sha)
            entries = [e for e in os.listdir(base_dir) if not e.startswith(".")]
            if len(entries) == 1:
                single_entry = os.path.join(base_dir, entries[0])
                if os.path.isdir(single_entry):
                    self.repo_dir = single_entry
                else:
                    self.repo_dir = base_dir
            else:
                self.repo_dir = base_dir

            return self.repo_dir

        except (SecurityArchiveError, ResourceExhaustionError):
            self.cleanup()
            raise
        except Exception as e:
            self.cleanup()
            raise SecurityArchiveError(f"Failed to safely extract archive: {str(e)}") from e
