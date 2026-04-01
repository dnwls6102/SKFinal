"use client";

import { FormEvent, useDeferredValue, useEffect, useState } from "react";

type GitHubUser = {
  login: string;
};

type Repository = {
  id: number;
  full_name: string;
};

type CommitItem = {
  repo_full_name: string;
  sha: string;
  message: string;
  author_date: string;
  url: string;
};

type SlackWorkspace = {
  team_id: string;
  team_name: string;
  user_name: string;
};

type SlackChannel = {
  id: string;
  name?: string;
};

type SlackItem = {
  team_id: string;
  team_name: string;
  channel_id: string;
  channel_name: string;
  title: string;
  created_at: string;
  permalink: string;
  message_text: string;
};

type GeneratedReport = {
  report: string;
  structured_report: Record<string, string>;
  queries: string[];
};

const defaultTemplateFields = [
  "업무 내용 및 활동",
  "성공적으로 잘 수행했다고 생각하는 점",
  "스스로 부족하다고 생각하는 점/보완 계획",
];

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
    cache: "no-store",
    ...init,
  });

  if (!response.ok) {
    let detail = `요청 실패 (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      try {
        const rawText = (await response.text()).trim();
        if (rawText) {
          detail = `${detail}: ${rawText.slice(0, 300)}`;
        }
      } catch {}
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

function formatDate(isoString: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(isoString));
}

export function Dashboard() {
  const [booting, setBooting] = useState(true);
  const [githubUser, setGithubUser] = useState<GitHubUser | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [repoGroups, setRepoGroups] = useState<Record<string, string[]>>({});
  const [selectedRepoGroups, setSelectedRepoGroups] = useState<string[]>([]);
  const [selectedRepos, setSelectedRepos] = useState<string[]>([]);
  const [commits, setCommits] = useState<CommitItem[]>([]);
  const [slackWorkspaces, setSlackWorkspaces] = useState<SlackWorkspace[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [slackChannels, setSlackChannels] = useState<SlackChannel[]>([]);
  const [selectedChannelIds, setSelectedChannelIds] = useState<string[]>([]);
  const [slackItems, setSlackItems] = useState<SlackItem[]>([]);
  const [templateFields, setTemplateFields] = useState<string[]>(defaultTemplateFields);
  const [reportStyle, setReportStyle] = useState("match");
  const [exampleFiles, setExampleFiles] = useState<File[]>([]);
  const [report, setReport] = useState<GeneratedReport | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [activityFilter, setActivityFilter] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationMessage, setGenerationMessage] = useState("");

  const deferredActivityFilter = useDeferredValue(activityFilter);

  useEffect(() => {
    void initialize();
  }, []);

  async function initialize() {
    setBooting(true);
    setErrorMessage("");

    try {
      const params = new URLSearchParams(window.location.search);
      const code = params.get("code");
      const state = params.get("state");
      const error = params.get("error");

      if (error) {
        throw new Error(`OAuth 오류: ${error}`);
      }

      if (code && state) {
        await completeOAuth(code, state);
        window.history.replaceState({}, "", "/");
      }

      const githubSession = await request<{ connected: boolean; user: GitHubUser | null }>("/github/session");
      setGithubUser(githubSession.user);
      if (githubSession.connected && githubSession.user) {
        await loadGitHubData(false);
      }

      const workspacePayload = await request<{ workspaces: SlackWorkspace[] }>("/slack/workspaces");
      setSlackWorkspaces(workspacePayload.workspaces);
      if (workspacePayload.workspaces[0]) {
        setSelectedWorkspaceId(workspacePayload.workspaces[0].team_id);
        await loadSlackChannels(workspacePayload.workspaces[0].team_id);
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "초기화에 실패했습니다.");
    } finally {
      setBooting(false);
    }
  }

  async function completeOAuth(code: string, state: string) {
    if (state.startsWith("github:")) {
      const payload = await request<{ user: GitHubUser }>("/github/exchange", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, state }),
      });
      setGithubUser(payload.user);
      setStatusMessage(`GitHub 계정 ${payload.user.login} 연결 완료`);
      return;
    }

    if (state.startsWith("slack:")) {
      const payload = await request<{ workspace: SlackWorkspace }>("/slack/exchange", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, state }),
      });
      setStatusMessage(`Slack 워크스페이스 ${payload.workspace.team_name} 연결 완료`);
      return;
    }

    throw new Error("지원하지 않는 OAuth state입니다.");
  }

  async function beginOAuth(provider: "github" | "slack") {
    const payload = await request<{ url: string }>(`/${provider}/login-url`);
    window.location.assign(payload.url);
  }

  async function loadGitHubData(refresh: boolean, explicitRepos?: string[], explicitGroups?: string[]) {
    const repoPayload = await request<{
      repos: Repository[];
      repo_groups: Record<string, string[]>;
    }>("/github/repositories");

    setRepositories(repoPayload.repos);
    setRepoGroups(repoPayload.repo_groups);

    const groupNames = Object.keys(repoPayload.repo_groups);
    const nextSelectedGroups =
      explicitGroups !== undefined
        ? explicitGroups.filter((groupName) => groupNames.includes(groupName))
        : explicitRepos === undefined
          ? selectedRepoGroups.length === 0
            ? groupNames
            : selectedRepoGroups.filter((groupName) => groupNames.includes(groupName))
          : selectedRepoGroups.length === 0
          ? groupNames
          : selectedRepoGroups.filter((groupName) => groupNames.includes(groupName));

    const derivedRepos =
      explicitRepos ??
      Array.from(
        new Set(
          nextSelectedGroups.flatMap((groupName) => repoPayload.repo_groups[groupName] ?? []),
        ),
      );

    setSelectedRepoGroups(nextSelectedGroups);
    setSelectedRepos(derivedRepos);

    const commitPayload = await request<{ items: CommitItem[] }>("/github/commits", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selected_repo_full_names: derivedRepos,
        refresh,
      }),
    });
    setCommits(commitPayload.items);
  }

  async function loadSlackChannels(teamId: string) {
    const channelPayload = await request<{ channels: SlackChannel[] }>(`/slack/workspaces/${teamId}/channels`);
    const channelIds = channelPayload.channels.map((channel) => channel.id);
    setSlackChannels(channelPayload.channels);
    setSelectedChannelIds(channelIds);
    await loadSlackItems(teamId, channelIds, false);
  }

  async function loadSlackItems(teamId: string, channelIds: string[], refresh: boolean) {
    const payload = await request<{ items: SlackItem[] }>(`/slack/workspaces/${teamId}/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selected_channel_ids: channelIds,
        refresh,
      }),
    });
    setSlackItems(payload.items);
  }

  async function disconnectGitHub() {
    await request("/github/session", { method: "DELETE" });
    setGithubUser(null);
    setRepositories([]);
    setRepoGroups({});
    setSelectedRepoGroups([]);
    setSelectedRepos([]);
    setCommits([]);
    setStatusMessage("GitHub 연결을 해제했습니다.");
  }

  async function disconnectSlack(teamId: string) {
    await request(`/slack/workspaces/${teamId}`, { method: "DELETE" });
    const nextWorkspaces = slackWorkspaces.filter((workspace) => workspace.team_id !== teamId);
    setSlackWorkspaces(nextWorkspaces);
    setSlackChannels([]);
    setSelectedChannelIds([]);
    setSlackItems([]);

    if (nextWorkspaces[0]) {
      setSelectedWorkspaceId(nextWorkspaces[0].team_id);
      await loadSlackChannels(nextWorkspaces[0].team_id);
    } else {
      setSelectedWorkspaceId("");
    }
  }

  function toggleRepoGroup(groupName: string) {
    const nextGroups = selectedRepoGroups.includes(groupName)
      ? selectedRepoGroups.filter((item) => item !== groupName)
      : [...selectedRepoGroups, groupName];
    const nextRepos = Array.from(new Set(nextGroups.flatMap((name) => repoGroups[name] ?? [])));
    setSelectedRepoGroups(nextGroups);
    setSelectedRepos(nextRepos);
    void loadGitHubData(true, nextRepos, nextGroups);
  }

  function toggleChannel(channelId: string) {
    if (!selectedWorkspaceId) {
      return;
    }
    const nextChannels = selectedChannelIds.includes(channelId)
      ? selectedChannelIds.filter((item) => item !== channelId)
      : [...selectedChannelIds, channelId];
    setSelectedChannelIds(nextChannels);
    void loadSlackItems(selectedWorkspaceId, nextChannels, true);
  }

  function updateTemplateField(index: number, value: string) {
    setTemplateFields((current) => current.map((field, fieldIndex) => (fieldIndex === index ? value : field)));
  }

  async function generateReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage("");
    setStatusMessage("");

    const cleanedFields = templateFields.map((field) => field.trim()).filter(Boolean);
    if (cleanedFields.length === 0) {
      setErrorMessage("보고 항목을 최소 한 개 이상 입력해야 합니다.");
      return;
    }

    const formData = new FormData();
    formData.set("template_fields", JSON.stringify(cleanedFields));
    formData.set("report_style", reportStyle);
    formData.set("selected_repo_full_names", JSON.stringify(selectedRepos));
    formData.set("selected_team_id", selectedWorkspaceId);
    formData.set("selected_channel_ids", JSON.stringify(selectedChannelIds));
    for (const file of exampleFiles) {
      formData.append("example_files", file);
    }

    setIsGenerating(true);
    setGenerationMessage("주간보고 생성 요청을 보내는 중입니다.");

    try {
      const payload = await request<GeneratedReport>("/report/generate", {
        method: "POST",
        body: formData,
      });
      setReport(payload);
      setStatusMessage("주간보고 생성이 완료되었습니다.");
      setGenerationMessage("생성이 완료되었습니다.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "주간보고 생성에 실패했습니다.");
      setGenerationMessage("");
    } finally {
      setIsGenerating(false);
    }
  }

  const mergedActivity = [...commits, ...slackItems]
    .map((item) => {
      if ("sha" in item) {
        return {
          type: "github" as const,
          timestamp: item.author_date,
          title: item.repo_full_name,
          body: item.message,
          link: item.url,
          meta: "GitHub commit",
        };
      }

      return {
        type: "slack" as const,
        timestamp: item.created_at,
        title: `${item.channel_name} / ${item.title}`,
        body: item.message_text,
        link: item.permalink,
        meta: "Slack file",
      };
    })
    .filter((item) => {
      if (!deferredActivityFilter.trim()) {
        return true;
      }
      const keyword = deferredActivityFilter.toLowerCase();
      return `${item.title} ${item.body}`.toLowerCase().includes(keyword);
    })
    .sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1));

  const connectedWorkspace = slackWorkspaces.find((workspace) => workspace.team_id === selectedWorkspaceId) ?? null;

  return (
    <main className="shell">
      <section className="hero">
        <div>
          <p className="eyebrow">Weekly Report Studio</p>
          <h1>수집, 검토, 생성 흐름으로 정리한 주간보고 워크스페이스</h1>
          <p className="hero-copy">
            GitHub 커밋과 Slack 공유 파일을 한 타임라인에 모으고, 선택한 항목 구조에 맞춰 보고서를 생성합니다.
          </p>
        </div>
        <div className="hero-status">
          <div className="metric-card accent">
            <span>GitHub 커밋</span>
            <strong>{commits.length}</strong>
          </div>
          <div className="metric-card warm">
            <span>Slack 기록</span>
            <strong>{slackItems.length}</strong>
          </div>
          <div className="metric-card neutral">
            <span>보고 항목</span>
            <strong>{templateFields.filter((field) => field.trim()).length}</strong>
          </div>
        </div>
      </section>

      {booting ? <div className="banner">환경을 불러오는 중입니다.</div> : null}
      {isGenerating ? <div className="banner">주간보고 생성 중입니다. 근거 문서를 정리하고 보고서를 작성하고 있습니다.</div> : null}
      {statusMessage ? <div className="banner success">{statusMessage}</div> : null}
      {errorMessage ? <div className="banner error">{errorMessage}</div> : null}

      <section className="workspace-grid">
        <aside className="control-column">
          <article className="panel">
            <div className="panel-header">
              <div>
                <p className="panel-kicker">Source 01</p>
                <h2>GitHub</h2>
              </div>
              {githubUser ? (
                <button className="ghost-button" onClick={() => void disconnectGitHub()}>
                  연결 해제
                </button>
              ) : (
                <button className="solid-button" onClick={() => void beginOAuth("github")}>
                  GitHub 연결
                </button>
              )}
            </div>

            {githubUser ? (
              <>
                <p className="connection-state">
                  <strong>{githubUser.login}</strong> 계정으로 연결됨
                </p>
                <div className="group-list">
                  {Object.keys(repoGroups).map((groupName) => (
                    <div key={groupName} className="group-block">
                      <label className="checkbox-row">
                        <input
                          type="checkbox"
                          checked={selectedRepoGroups.includes(groupName)}
                          onChange={() => toggleRepoGroup(groupName)}
                        />
                        <span>{groupName}</span>
                      </label>
                    </div>
                  ))}
                </div>
                <button className="outline-button" type="button" onClick={() => void loadGitHubData(true)}>
                  커밋 새로고침
                </button>
              </>
            ) : (
              <p className="muted-copy">GitHub 저장소를 연결하면 이번 주 커밋을 그룹별로 필터링할 수 있습니다.</p>
            )}
          </article>

          <article className="panel">
            <div className="panel-header">
              <div>
                <p className="panel-kicker">Source 02</p>
                <h2>Slack</h2>
              </div>
              <button className="solid-button coral" type="button" onClick={() => void beginOAuth("slack")}>
                워크스페이스 연결
              </button>
            </div>

            {slackWorkspaces.length > 0 ? (
              <>
                <select
                  className="select-box"
                  value={selectedWorkspaceId}
                  onChange={(event) => {
                    setSelectedWorkspaceId(event.target.value);
                    void loadSlackChannels(event.target.value);
                  }}
                >
                  {slackWorkspaces.map((workspace) => (
                    <option key={workspace.team_id} value={workspace.team_id}>
                      {workspace.team_name} / {workspace.user_name}
                    </option>
                  ))}
                </select>
                {connectedWorkspace ? (
                  <div className="inline-actions">
                    <span className="connection-state">{connectedWorkspace.team_name} 연결됨</span>
                    <button className="ghost-button" type="button" onClick={() => void disconnectSlack(connectedWorkspace.team_id)}>
                      해제
                    </button>
                  </div>
                ) : null}
                <div className="checkbox-list compact">
                  {slackChannels.map((channel) => (
                    <label key={channel.id} className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={selectedChannelIds.includes(channel.id)}
                        onChange={() => toggleChannel(channel.id)}
                      />
                      <span>#{channel.name ?? channel.id}</span>
                    </label>
                  ))}
                </div>
                {selectedWorkspaceId ? (
                  <button
                    className="outline-button"
                    type="button"
                    onClick={() => void loadSlackItems(selectedWorkspaceId, selectedChannelIds, true)}
                  >
                    Slack 새로고침
                  </button>
                ) : null}
              </>
            ) : (
              <p className="muted-copy">Slack 공유 파일과 메시지를 보고서 근거로 가져올 수 있습니다.</p>
            )}
          </article>
        </aside>

        <section className="main-column">
          <article className="panel tall">
            <div className="panel-header">
              <div>
                <p className="panel-kicker">Review</p>
                <h2>이번 주 활동 타임라인</h2>
              </div>
              <input
                className="search-box"
                placeholder="커밋 메시지나 Slack 기록 검색"
                value={activityFilter}
                onChange={(event) => setActivityFilter(event.target.value)}
              />
            </div>
            <div className="timeline">
              {mergedActivity.length === 0 ? (
                <div className="empty-state">선택한 소스에서 아직 불러온 활동이 없습니다.</div>
              ) : (
                mergedActivity.map((item, index) => (
                  <a
                    key={`${item.type}-${index}-${item.timestamp}`}
                    className={`timeline-card ${item.type}`}
                    href={item.link}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <div className="timeline-meta">
                      <span>{item.meta}</span>
                      <span>{formatDate(item.timestamp)}</span>
                    </div>
                    <h3>{item.title}</h3>
                    <p>{item.body}</p>
                  </a>
                ))
              )}
            </div>
          </article>

          <article className="panel tall">
            <div className="panel-header">
              <div>
                <p className="panel-kicker">Generate</p>
                <h2>보고서 설계와 결과 미리보기</h2>
              </div>
            </div>

            <form className="report-form" onSubmit={generateReport}>
              <div className="field-grid">
                <div className="field-section">
                  <label className="section-label">보고 항목</label>
                  <div className="field-stack">
                    {templateFields.map((field, index) => (
                      <div key={`${index}-${field}`} className="field-row">
                        <input
                          className="text-input"
                          value={field}
                          onChange={(event) => updateTemplateField(index, event.target.value)}
                          placeholder={`항목 ${index + 1}`}
                        />
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => setTemplateFields((current) => current.filter((_, fieldIndex) => fieldIndex !== index))}
                          disabled={templateFields.length <= 1}
                        >
                          삭제
                        </button>
                      </div>
                    ))}
                  </div>
                  <button type="button" className="outline-button" onClick={() => setTemplateFields((current) => [...current, ""])}>
                    항목 추가
                  </button>
                </div>

                <div className="field-section">
                  <label className="section-label">톤과 예시</label>
                  <div className="style-switch">
                    {[
                      ["concise", "간결하게"],
                      ["match", "예시 톤 유지"],
                      ["detailed", "상세하게"],
                    ].map(([value, label]) => (
                      <button
                        key={value}
                        type="button"
                        className={reportStyle === value ? "style-pill active" : "style-pill"}
                        onClick={() => setReportStyle(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <label className="upload-box">
                    <span>예시 파일 업로드</span>
                    <input
                      type="file"
                      multiple
                      accept=".xlsx,.pdf,.docx,.txt,.md"
                      onChange={(event) => setExampleFiles(Array.from(event.target.files ?? []))}
                    />
                  </label>
                  {exampleFiles.length > 0 ? (
                    <div className="file-list">
                      {exampleFiles.map((file) => (
                        <span key={`${file.name}-${file.lastModified}`} className="file-chip">
                          {file.name}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <button type="submit" className="solid-button large" disabled={isGenerating}>
                    {isGenerating ? "생성 중..." : "주간보고 생성"}
                  </button>
                </div>
              </div>

              <div className="report-preview">
                <div className="preview-header">
                  <div>
                    <p className="panel-kicker">Preview</p>
                    <h3>생성 결과</h3>
                  </div>
                </div>
                {isGenerating ? (
                  <div className="empty-state large">
                    {generationMessage || "주간보고를 생성하고 있습니다."}
                  </div>
                ) : report ? (
                  <>
                    <div className="query-strip">
                      {report.queries.map((query) => (
                        <span key={query} className="query-pill">
                          {query}
                        </span>
                      ))}
                    </div>
                    <div className="report-output">
                      {Object.entries(report.structured_report).map(([title, body]) => (
                        <section key={title} className="report-section">
                          <h4>{title}</h4>
                          <p>{body}</p>
                        </section>
                      ))}
                    </div>
                  </>
                ) : (
                  <div className="empty-state large">조건을 정리한 뒤 보고서를 생성하면 결과가 여기에 표시됩니다.</div>
                )}
              </div>
            </form>
          </article>
        </section>
      </section>
    </main>
  );
}
