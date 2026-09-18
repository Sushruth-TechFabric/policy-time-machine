import { useState } from 'react';
import { recordDisposition } from '../../api/client.js';
import './review.css';

const OUTCOMES = [
  ['closer_look', 'Warrants a closer look'],
  ['nothing_noteworthy', 'Nothing noteworthy'],
  ['more_information', 'Needs more information'],
];

/** The one human act in the workflow. The agent never proposes a value. */
export default function DispositionForm({ claimId, disposition, onRecorded }) {
  const [outcome, setOutcome] = useState(disposition?.outcome ?? null);
  const [note, setNote] = useState(disposition?.note ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    if (!outcome) return;
    setBusy(true); setError(null);
    try {
      onRecorded(await recordDisposition(claimId, outcome, note.trim() || null));
    } catch (err) {
      setError(err?.message || 'Could not record the disposition.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="disposition" onSubmit={submit}>
      <div className="disposition-title">Disposition</div>
      <div className="disposition-options" role="radiogroup" aria-label="Disposition">
        {OUTCOMES.map(([value, label]) => (
          <label key={value} className="disposition-option">
            <input type="radio" name="outcome" value={value} checked={outcome === value} onChange={() => setOutcome(value)} aria-label={label} />
            {label}
          </label>
        ))}
      </div>
      <textarea className="disposition-note" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Disposition note" />
      <div className="disposition-actions">
        <button type="submit" className="ask-submit" disabled={!outcome || busy}>Record disposition</button>
        {disposition && <span className="disposition-recorded">Recorded by {disposition.recorded_by} · {new Date(disposition.recorded_at).toLocaleString()}</span>}
      </div>
      {error && <div className="app-boot-error">{error}</div>}
    </form>
  );
}
