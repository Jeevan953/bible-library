function HomePage({
  versions,
  onBrowseVersions,
  onOpenTamil,
  onOpenAbout,
}) {
  const availableVersions = versions.filter(
    (version) => version.available,
  );

  const languages = new Set(
    availableVersions.map((version) => version.language),
  ).size;

  const years = availableVersions
    .map((version) => version.year)
    .filter(Boolean);

  const yearRange = years.length
    ? `${Math.min(...years)}–${Math.max(...years)}`
    : "Unknown";

  const tamilAvailable = availableVersions.some(
    (version) => version.abbreviation === "PPTB1856",
  );

  const statistics = [
    {
      icon: "📖",
      value: availableVersions.length,
      label: "Bible Versions",
      note: "Available to read",
    },
    {
      icon: "📚",
      value: "1,189",
      label: "Canonical Chapters",
      note: "Genesis to Revelation",
    },
    {
      icon: "📄",
      value: "426,343",
      label: "Verse Texts",
      note: "Stored in the library",
    },
    {
      icon: "🌐",
      value: languages || "—",
      label: "Languages",
      note: "Multiple translations",
    },
    {
      icon: "🔤",
      value: "4,247",
      label: "Proper Names",
      note: "STEPBible TIPNR",
    },
    {
      icon: "🗓️",
      value: yearRange,
      label: "Years",
      note: "Historical to modern",
    },
  ];

  return (
    <section className="library-home">
      <div className="library-home-hero">
        <p className="eyebrow">Know Your Bible</p>

        <h1>Bible Library</h1>

        <h2>
          📖 Explore, read, search, and compare Bible versions
        </h2>

        <p>
          A growing digital Bible library containing translations,
          proper names, historical texts, and comparison tools.
        </p>

        <div className="library-home-actions">
          <button
            className="library-primary-button"
            type="button"
            onClick={onBrowseVersions}
          >
            📚 Browse Bible Versions
          </button>

          <button
            className="library-secondary-button"
            type="button"
            disabled={!tamilAvailable}
            onClick={onOpenTamil}
          >
            View Peter Percival Bible
          </button>
        </div>
      </div>

      <div className="library-stat-grid">
        {statistics.map((statistic) => (
          <article
            className="library-stat-card"
            key={statistic.label}
          >
            <span className="library-stat-icon">
              {statistic.icon}
            </span>

            <div>
              <strong>{statistic.value}</strong>
              <h3>{statistic.label}</h3>
              <p>{statistic.note}</p>
            </div>
          </article>
        ))}
      </div>

      <div className="library-information-grid">
        <article className="library-information about-summary">
          <span className="library-information-icon">ⓘ</span>

          <div>
            <h2>About This Project</h2>

            <p>
              Read individual chapters, search Scripture and
              proper names, or compare translations side by side.
            </p>

            <button type="button" onClick={onOpenAbout}>
              Learn more about the project →
            </button>
          </div>
        </article>

        <article className="library-information recently-added">
          <span className="library-information-icon">✓</span>

          <div>
            <h2>Recently Added</h2>

            <p>
              Peter Percival Tamil Bible (1856), Genesis chapters
              1–50, is available as a draft transcription.
            </p>

            <strong>Genesis 1–50 available</strong>
          </div>
        </article>
      </div>

      <article className="library-collection">
        <div>
          <p className="eyebrow">Library collection</p>
          <h2>Read Scripture your way</h2>

          <p>
            Choose a translation, search across all versions, or
            open the Parallel Bible for side-by-side comparison.
          </p>
        </div>

        <button type="button" onClick={onBrowseVersions}>
          View All Versions →
        </button>
      </article>
    </section>
  );
}

export default HomePage;
