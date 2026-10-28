"""PullRequest repository implementation."""


from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.repositories.base_repo import BaseRepository
from app.models.pull_request import PullRequest


class PullRequestRepository(BaseRepository[PullRequest]):
    """Data access operations for PullRequest entities."""

    def __init__(self, db: Session):
        super().__init__(PullRequest, db)

    def get_by_github_pr_id(self, github_pr_id: int) -> PullRequest | None:
        """Look up PR by GitHub global PR id."""
        stmt = select(PullRequest).where(PullRequest.github_pr_id == github_pr_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_repo_and_number(self, repository_id: str, number: int) -> PullRequest | None:
        """Look up PR by local repository ID and PR number."""
        stmt = select(PullRequest).where(
            PullRequest.repository_id == repository_id,
            PullRequest.number == number,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_pull_requests(
        self,
        page: int = 1,
        page_size: int = 20,
        repository_id: str | None = None,
        state: str | None = None,
        organization_id: str | None = None,
    ) -> tuple[list[PullRequest], int]:
        """List PRs filtered by repository, state, or organization."""
        filters = []
        if repository_id:
            filters.append(PullRequest.repository_id == repository_id)
        if state:
            filters.append(PullRequest.state == state)
        if organization_id:
            from app.models.repository import Repository

            filters.append(
                PullRequest.repository_id.in_(
                    select(Repository.id).where(Repository.organization_id == organization_id)
                )
            )
        return self.get_all(
            page=page,
            page_size=page_size,
            filters=filters,
            order_by=PullRequest.updated_at.desc(),
        )

    def upsert_pull_request(
        self,
        repository_id: str,
        github_pr_id: int,
        number: int,
        title: str,
        description: str | None,
        author_login: str,
        base_sha: str,
        head_sha: str,
        state: str = "open",
        is_draft: bool = False,
    ) -> PullRequest:
        """Create or update a pull request upon webhook receipt."""
        pr = self.get_by_repo_and_number(repository_id, number)
        if pr:
            pr.github_pr_id = github_pr_id
            pr.title = title
            pr.description = description
            pr.author_login = author_login
            pr.base_sha = base_sha
            pr.head_sha = head_sha
            pr.state = state
            pr.is_draft = is_draft
            return self.update(pr)

        new_pr = PullRequest(
            repository_id=repository_id,
            github_pr_id=github_pr_id,
            number=number,
            title=title,
            description=description,
            author_login=author_login,
            base_sha=base_sha,
            head_sha=head_sha,
            state=state,
            is_draft=is_draft,
        )
        return self.create(new_pr)
