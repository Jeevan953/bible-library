import { useEffect, useState } from "react";
import HighlightedBibleText from "./HighlightedBibleText";

import {
  getBooks,
  getChapter,
  getChapters,
} from "./services/bibleApi";


 function BibleReader({
  version,
  versions,
  initialLocation,
  onVersionChange,
  onBack,
}) {
  const [books, setBooks] = useState([]);
  const [chapters, setChapters] = useState([]);

  const [selectedBook, setSelectedBook] = useState(1);
  const [selectedChapter, setSelectedChapter] = useState(1);

  const [chapterData, setChapterData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");


 useEffect(() => {
  if (!version) {
    setLoading(false);
    return;
  }

  async function initializeReader() {

      try {
        const booksData = await getBooks(version.abbreviation);

        if (booksData.books.length === 0) {
          throw new Error(
            `No books are available for ${version.abbreviation}.`,
          );
        }

        const requestedBook = booksData.books.find(
  (book) =>
    book.position === initialLocation?.bookPosition,
);

const targetBook =
  requestedBook || booksData.books[0];

const chaptersData = await getChapters(
  version.abbreviation,
  targetBook.position,
);

const requestedChapter = Number(
  initialLocation?.chapter,
);

const targetChapter =
  chaptersData.chapters.includes(requestedChapter)
    ? requestedChapter
    : chaptersData.chapters[0];

const readerData = await getChapter(
  version.abbreviation,
  targetBook.position,
  targetChapter,
);

setBooks(booksData.books);
setChapters(chaptersData.chapters);
setSelectedBook(targetBook.position);
setSelectedChapter(targetChapter);
setChapterData(readerData);

if (initialLocation?.verse) {
  setTimeout(() => {
    document
      .getElementById(
        `verse-${initialLocation.verse}`,
      )
      ?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
  }, 150);
}
      } catch (requestError) {
        setError(requestError.message);
      } finally {
        setLoading(false);
      }
    }

    initializeReader();
  }, [version?.abbreviation, initialLocation]);


  async function changeBook(
  bookPosition,
  useLastChapter = false,
) {
  setLoading(true);
  setError("");

  try {
    const chaptersData = await getChapters(
      version.abbreviation,
      bookPosition,
    );

    const chapterNumber = useLastChapter
      ? chaptersData.chapters.at(-1)
      : chaptersData.chapters[0];

    const readerData = await getChapter(
      version.abbreviation,
      bookPosition,
      chapterNumber,
    );

    setSelectedBook(bookPosition);
    setChapters(chaptersData.chapters);
    setSelectedChapter(chapterNumber);
    setChapterData(readerData);

    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (requestError) {
    setError(requestError.message);
  } finally {
    setLoading(false);
  }
}


  async function changeChapter(chapterNumber) {
    setLoading(true);
    setError("");

    try {
      const readerData = await getChapter(
        version.abbreviation,
        selectedBook,
        chapterNumber,
      );

      setSelectedChapter(chapterNumber);
      setChapterData(readerData);

      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }


async function previousChapter() {
  const chapterIndex = chapters.indexOf(selectedChapter);

  if (chapterIndex > 0) {
    await changeChapter(chapters[chapterIndex - 1]);
    return;
  }

  const bookIndex = books.findIndex(
    (book) => book.position === selectedBook,
  );

  if (bookIndex > 0) {
    const previousBook = books[bookIndex - 1];

    await changeBook(previousBook.position, true);
  }
}


async function nextChapter() {
  const chapterIndex = chapters.indexOf(selectedChapter);

  if (chapterIndex < chapters.length - 1) {
    await changeChapter(chapters[chapterIndex + 1]);
    return;
  }

  const bookIndex = books.findIndex(
    (book) => book.position === selectedBook,
  );

  if (bookIndex < books.length - 1) {
    const nextBook = books[bookIndex + 1];

    await changeBook(nextBook.position);
  }
}

  if (!version) {
  return (
    <p className="status">
      Select a Bible version.
    </p>
  );
}
  return (
    <section className="reader-page">
      <button
        className="back-button"
        type="button"
        onClick={onBack}
      >
        ← Back to versions
      </button>

      <div className="reader-toolbar">
        <label>
          Version
           <select
  value={version.abbreviation}
  disabled={loading}
  onChange={(event) => {
    const selected = versions.find(
      (item) =>
        item.abbreviation === event.target.value,
    );

    if (selected) {
      onVersionChange(selected);
    }
  }}
>
  {versions.map((item) => (
    <option
      key={item.id}
      value={item.abbreviation}
    >
      {item.abbreviation}
    </option>
  ))}
</select>
        </label>

        <label>
          Book
          <select
            value={selectedBook}
            disabled={loading}
            onChange={(event) =>
              changeBook(Number(event.target.value))
            }
          >
            {books.map((book) => (
              <option key={book.id} value={book.position}>
                {book.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Chapter
          <select
            value={selectedChapter}
            disabled={loading}
            onChange={(event) =>
              changeChapter(Number(event.target.value))
            }
          >
            {chapters.map((chapter) => (
              <option key={chapter} value={chapter}>
                {chapter}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && (
        <p className="status">Loading chapter…</p>
      )}

      {error && (
        <p className="status error">{error}</p>
      )}

      {chapterData && (
        <article className="reader-card">
          <header className="reader-heading">
            <p>{chapterData.version.name}</p>

            <h1>
              {chapterData.book.name} {chapterData.chapter}
            </h1>
          </header>

          <div className="verse-list">
            {chapterData.verses.map((verse) => (
              <p
  id={`verse-${verse.number}`}
  className={
    initialLocation &&
    chapterData.book.position ===
      initialLocation.bookPosition &&
    chapterData.chapter ===
      initialLocation.chapter &&
    verse.number === initialLocation.verse
      ? "verse highlighted-verse"
      : "verse"
  }
  key={verse.number}
>
                <sup>{verse.number}</sup>
                <span
  className={
    verse.number === 1
      ? "verse-text first-verse-text"
      : "verse-text"
  }
>
  <HighlightedBibleText text={verse.text} />
</span>
              </p>
            ))}
          </div>

          <div className="chapter-navigation">
  <button
    type="button"
    disabled={
      loading ||
      (
        selectedBook === books[0]?.position &&
        selectedChapter === chapters[0]
      )
    }
    onClick={previousChapter}
  >
    ← Previous Chapter
  </button>

  <button
    type="button"
    disabled={
      loading ||
      (
        selectedBook === books.at(-1)?.position &&
        selectedChapter === chapters.at(-1)
      )
    }
    onClick={nextChapter}
  >
    Next Chapter →
  </button>
</div>

        </article>
      )}
    </section>
  );
}

export default BibleReader;
