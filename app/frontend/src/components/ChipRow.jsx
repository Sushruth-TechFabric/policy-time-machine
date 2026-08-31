import './ChipRow.css';

/**
 * Three to five chips from the context bank, the only call-to-action
 * styling on the screen besides links (docs/specs/06-ux-specification.md
 * §1). Each chip is a complete, context-free question (ADR-0011) — clicking
 * one sends it exactly like a typed question.
 */
export default function ChipRow({ chips, onSelect, disabled }) {
  if (!chips || chips.length === 0) return null;

  return (
    <div className="chip-row">
      {chips.map((chip) => (
        <button type="button" key={chip} className="chip" onClick={() => onSelect(chip)} disabled={disabled}>
          {chip}
        </button>
      ))}
    </div>
  );
}
