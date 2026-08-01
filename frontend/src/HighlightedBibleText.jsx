const DIVINE_NAMES = [
  "Lord Jesus Christ",
  "Jesus Christ",
  "Holy Spirit",
  "Spirit of God",
  "Son of God",
  "Son of Man",
  "Lord God",
  "YHWH Elohim",
  "Ruach Elohim",
  "El Shaddai",
  "El Elyon",
  "Most High",
  "Jesus",
  "Christ",
  "Messiah",
  "Jehovah",
  "Elohim",
  "Adonai",
  "YHWH",
  "God",
  "Lord",
  "Theos",
  "Theou",
  "Kyrios",
  "Kyriou",
  "Kyrie",
].sort((first, second) => second.length - first.length);

const DIVINE_NAME_SET = new Set(
  DIVINE_NAMES.map((name) => name.toLowerCase()),
);

const escapedNames = DIVINE_NAMES.map((name) =>
  name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
);

const DIVINE_NAME_PATTERN = new RegExp(
  `\\b(${escapedNames.join("|")})\\b`,
  "gi",
);

const splitPattern =
  /(\b(?:God|Lord|Elohim|Jesus)\b|(?:தேவன்|கர்த்தர்|ஆண்டவர்|இயேசு|எலோகிம்)[\u200C\u200D]?)/giu;

const exactPattern =
  /^(?:God|Lord|Elohim|Jesus|(?:தேவன்|கர்த்தர்|ஆண்டவர்|இயேசு|எலோகிம்)[\u200C\u200D]?)$/iu;

function HighlightedBibleText({ text = "" }) {
  return text
    .split(splitPattern)
    .map((part, index) =>
      exactPattern.test(part) ? (
        <span className="red-letter" key={index}>
          {part}
        </span>
      ) : (
        part
      ),
    );
}

export { HighlightedBibleText };
export default HighlightedBibleText;
