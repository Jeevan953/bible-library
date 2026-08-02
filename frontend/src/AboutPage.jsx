function AboutPage({ onBack }) {
  return (
    <section className="about-page">
      <button
        className="back-button"
        type="button"
        onClick={onBack}
      >
        ← Back to Home
      </button>

      <article className="about-card">
        <header className="about-heading">
          <p>Know Your Bible</p>
          <h1>About This Project</h1>
          <p className="about-introduction">
            A growing digital library for reading, searching,
            and comparing Bible translations.
          </p>
        </header>

        <div className="about-feature-grid">
          <section>
            <span className="about-icon">📖</span>
            <h2>Read Scripture</h2>
            <p>
              Browse individual Bible translations by book,
              chapter, and verse.
            </p>
          </section>

          <section>
            <span className="about-icon">🔎</span>
            <h2>Search</h2>
            <p>
              Search individual versions, all versions, Bible
              references, and proper names.
            </p>
          </section>

          <section>
            <span className="about-icon">⚖️</span>
            <h2>Compare Versions</h2>
            <p>
              Display several translations side by side in the
              Parallel Bible reader.
            </p>
          </section>
        </div>

        <section className="about-source">
          <h2>Sources and Attribution</h2>

          <p>
            Bible texts retain their respective translation and
            copyright information. Proper-name information comes
            from STEPBible TIPNR and is used under CC BY 4.0.
          </p>

          <p>
            More Bible versions, languages, and study features
            will continue to be added.
          </p>
        </section>
      </article>
    </section>
  );
}

export default AboutPage;
