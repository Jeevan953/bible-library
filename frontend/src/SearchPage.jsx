import { useState } from "react";

import HighlightedBibleText from "./HighlightedBibleText";
import { searchBible } from "./services/bibleApi";


function VerseSearchResult({
  result,
  onOpenResult,
}) {
  const abbreviation =
    result.version?.abbreviation || "";

  return (
    <article className="search-result">
      <div className="search-result-heading">
        <button
          className="search-result-link"
          type="button"
          disabled={!abbreviation}
          onClick={() =>
            onOpenResult(abbreviation, result)
          }
        >
          {result.reference}
        </button>

        {abbreviation && (
          <span className="search-version-badge">
            {abbreviation}
          </span>
        )}
      </div>

      <p>
        <HighlightedBibleText text={result.text} />
      </p>
    </article>
  );
}


function ProperNameResult({ result }) {
  return (
    <article className="search-result proper-name-result">
      <div className="proper-name-title-row">
        <h3>{result.name}</h3>

        <span className="proper-name-category">
          {result.category}
        </span>
      </div>

      {result.type && (
        <p className="proper-name-type">
          {result.type}
        </p>
      )}

      {result.description && (
        <p className="proper-name-description">
          {result.description}
        </p>
      )}

      <div className="proper-name-details">
        {result.all_names && (
          <p>
            <strong>Names:</strong>{" "}
            {result.all_names}
          </p>
        )}

        {result.strong_numbers && (
          <p>
            <strong>Strong’s:</strong>{" "}
            {result.strong_numbers}
          </p>
        )}

        {result.references?.length > 0 && (
          <p>
            <strong>References:</strong>{" "}
            {result.references.join(", ")}
          </p>
        )}
      </div>
    </article>
  );
}


function HitchcockNameResult({ result }) {
  return (
    <article className="search-result proper-name-result">
      <div className="proper-name-title-row">
        <h3>{result.name}</h3>

        <span className="proper-name-category">
          Hitchcock
        </span>
      </div>

      <p className="proper-name-description">
        {result.definition}
      </p>
    </article>
  );
}


function TamilDictionaryResult({ result }) {
  return (
    <article
      className={
        "search-result tamil-dictionary-result"
      }
      lang="ta"
    >
      <div className="tamil-dictionary-title-row">
        <h3>{result.word}</h3>

        <span className="tamil-dictionary-badge">
          தமிழ்
        </span>
      </div>

      <p className="tamil-dictionary-definition">
        {result.definition}
      </p>
    </article>
  );
}


function getResultScope(searchData) {
  if (searchData.mode === "proper_names") {
    return "Proper Names";
  }

  if (searchData.mode === "hitchcock_names") {
    return "Hitchcock’s Bible Names";
  }

  if (searchData.mode === "tamil_dictionary") {
    return "Tamil Bible Dictionary";
  }

  if (searchData.mode === "all_versions") {
    return "All Versions";
  }

  return (
    searchData.version?.abbreviation ||
    "selected version"
  );
}


function SearchPage({
  versions,
  onOpenResult,
  onBack,
}) {
  const defaultVersion =
    versions.find(
      (version) => version.abbreviation === "KJV",
    ) || versions[0];

  const [selectedVersion, setSelectedVersion] =
    useState(
      defaultVersion?.abbreviation || "",
    );

  const [query, setQuery] = useState("");
  const [searchData, setSearchData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");


  const properNamesMode =
    selectedVersion === "PROPER_NAMES";

  const hitchcockNamesMode =
    selectedVersion === "HITCHCOCK_NAMES";

  const tamilDictionaryMode =
    selectedVersion === "TAMIL_DICTIONARY";


  async function performSearch(page = 1) {
    const cleanQuery = query.trim();

    if (!cleanQuery) {
      setError(
        properNamesMode
          ? "Enter a proper name to search."
          : hitchcockNamesMode
            ? "Enter a Bible name or meaning to search."
            : tamilDictionaryMode
              ? "Enter a Tamil word or definition to search."
              : "Enter a word, phrase, or Bible reference.",
      );
      return;
    }

    setLoading(true);
    setError("");

    try {
      const data = await searchBible(
        selectedVersion,
        cleanQuery,
        page,
      );

      setSearchData(data);

      window.scrollTo({
        top: 0,
        behavior: "smooth",
      });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }


  function handleSubmit(event) {
    event.preventDefault();
    performSearch(1);
  }


  return (
    <section className="search-page">
      <button
        className="back-button"
        type="button"
        onClick={onBack}
      >
        ← Back to versions
      </button>

      <div className="search-panel">
        <header className="search-heading">
          <p>Bible Search</p>

          <h1>
            {properNamesMode
              ? "Search Proper Names"
              : hitchcockNamesMode
                ? "Search Hitchcock’s Bible Names"
                : tamilDictionaryMode
                  ? "Search Tamil Bible Dictionary"
                  : "Search Scripture"}
          </h1>
        </header>

        <form
          className="search-form"
          onSubmit={handleSubmit}
        >
          <label>
            Search in

            <select
              value={selectedVersion}
              disabled={loading}
              onChange={(event) => {
                setSelectedVersion(
                  event.target.value,
                );
                setSearchData(null);
                setError("");
              }}
            >
              <option value="ALL">
                All Versions
              </option>

              <option value="PROPER_NAMES">
                Proper Names
              </option>

              <option value="HITCHCOCK_NAMES">
                Hitchcock’s Bible Names
              </option>

              <option value="TAMIL_DICTIONARY">
                Tamil Bible Dictionary
              </option>

              <optgroup label="Individual Versions">
                {versions.map((version) => (
                  <option
                    key={version.id}
                    value={version.abbreviation}
                  >
                    {version.abbreviation} —{" "}
                    {version.name}
                  </option>
                ))}
              </optgroup>
            </select>
          </label>

          <label className="search-query-label">
            {properNamesMode
              ? "Name, Strong’s number, or description"
              : hitchcockNamesMode
                ? "Bible name or meaning"
                : tamilDictionaryMode
                  ? "Tamil word or definition"
                  : "Word, phrase, or reference"}

            <input
              type="search"
              value={query}
              placeholder={
                properNamesMode
                  ? "Example: Abraham or H0085"
                  : hitchcockNamesMode
                    ? "Example: Abraham, peace, or deliverer"
                    : tamilDictionaryMode
                      ? "உதாரணம்: தேவன், பவுல் அல்லது எருசலேம்"
                      : "Example: faith, John 1, or John 1:1"
              }
              disabled={loading}
              onChange={(event) =>
                setQuery(event.target.value)
              }
            />
          </label>

          <button
            className="search-button"
            type="submit"
            disabled={loading}
          >
            {loading ? "Searching…" : "Search"}
          </button>
        </form>
      </div>

      {error && (
        <p className="status error">{error}</p>
      )}

      {searchData && (
        <div className="search-results">
          <div className="search-summary">
            <h2>
              Results for “{searchData.query}”
            </h2>

            <span>
              {searchData.count}{" "}
              {searchData.count === 1
                ? "match"
                : "matches"}{" "}
              in {getResultScope(searchData)}
            </span>
          </div>

          {searchData.results.length === 0 ? (
            <p className="status">
              {searchData.mode === "proper_names"
                ? "No matching proper names were found."
                : searchData.mode === "hitchcock_names"
                  ? "No matching Hitchcock names were found."
                  : searchData.mode === "tamil_dictionary"
                    ? "பொருத்தமான அகராதிப் பதிவுகள் கிடைக்கவில்லை."
                    : "No matching verses were found."}
            </p>
          ) : (
            <div className="result-list">
              {searchData.results.map((result) =>
                result.result_type ===
                "proper_name" ? (
                  <ProperNameResult
                    key={`proper-name-${result.id}`}
                    result={result}
                  />
                ) : result.result_type ===
                  "hitchcock_name" ? (
                  <HitchcockNameResult
                    key={"hitchcock-name-" + result.id}
                    result={result}
                  />
                ) : result.result_type ===
                  "tamil_dictionary" ? (
                  <TamilDictionaryResult
                    key={`tamil-dictionary-${result.id}`}
                    result={result}
                  />
                ) : (
                  <VerseSearchResult
                    key={
                      `${result.version?.id || "version"}` +
                      `-${result.reference}`
                    }
                    result={result}
                    onOpenResult={onOpenResult}
                  />
                ),
              )}
            </div>
          )}

          {searchData.mode === "proper_names" &&
            searchData.attribution && (
              <p className="proper-name-attribution">
                Proper-name data:{" "}
                <a
                  href={searchData.attribution.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {searchData.attribution.name}
                </a>
                {" — "}
                {searchData.attribution.license}
              </p>
            )}

          {searchData.mode === "hitchcock_names" &&
            searchData.attribution && (
              <p className="proper-name-attribution">
                <strong>
                  {searchData.attribution.name}
                </strong>
                {" by "}
                {searchData.attribution.creator}
                {" (originally published "}
                {searchData.attribution.original_publication}
                {"). Electronic edition: "}
                <a
                  href={searchData.attribution.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {
                    searchData.attribution
                      .electronic_source
                  }
                </a>
                {". Rights: "}
                {searchData.attribution.rights}.
              </p>
            )}

          {searchData.mode ===
            "tamil_dictionary" &&
            searchData.attribution && (
              <p className="tamil-dictionary-attribution">
                <strong>
                  {searchData.attribution.name}
                </strong>
                {" — "}
                created by{" "}
                {searchData.attribution.creator};
                published by{" "}
                {searchData.attribution.publisher}.
                {" "}
                {searchData.attribution.license}.
                {" "}
                <a
                  href={searchData.attribution.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Source
                </a>
              </p>
            )}

          {searchData.total_pages > 1 && (
            <div className="search-pagination">
              <button
                type="button"
                disabled={
                  loading || searchData.page <= 1
                }
                onClick={() =>
                  performSearch(searchData.page - 1)
                }
              >
                ← Previous
              </button>

              <span>
                Page {searchData.page} of{" "}
                {searchData.total_pages}
              </span>

              <button
                type="button"
                disabled={
                  loading ||
                  searchData.page >=
                    searchData.total_pages
                }
                onClick={() =>
                  performSearch(searchData.page + 1)
                }
              >
                Next →
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}


export default SearchPage;
