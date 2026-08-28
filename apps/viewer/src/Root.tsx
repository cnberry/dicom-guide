import { useEffect, useState } from 'react';
import App from './App';
import { RegistrationQaWorkspace } from './components/RegistrationQaWorkspace';
import {
  loadRegistrationQaContext,
  type RegistrationQaContext,
} from './registrationQaService';

type RootState =
  | { status: 'probing' }
  | { status: 'registration-qa'; context: RegistrationQaContext }
  | { status: 'dicom-viewer' }
  | { status: 'error'; message: string };

export default function Root() {
  const [state, setState] = useState<RootState>({ status: 'probing' });

  useEffect(() => {
    const controller = new AbortController();
    void loadRegistrationQaContext(controller.signal).then((result) => {
      if (controller.signal.aborted) return;
      if (result.status === 'available') {
        setState({ status: 'registration-qa', context: result.context });
      } else if (result.status === 'none') {
        setState({ status: 'dicom-viewer' });
      } else {
        setState({ status: 'error', message: result.message });
      }
    });
    return () => controller.abort();
  }, []);

  if (state.status === 'probing') {
    return (
      <main className="qa-probe">
        <p className="eyebrow">ScanView local workspace</p>
        <h1>Checking for a human QA session…</h1>
      </main>
    );
  }
  if (state.status === 'registration-qa') {
    return <RegistrationQaWorkspace context={state.context} />;
  }
  if (state.status === 'error') {
    return (
      <main className="qa-probe qa-error-state" role="alert">
        <p className="eyebrow">Registration QA unavailable</p>
        <h1>Local QA session failed closed</h1>
        <p>{state.message}</p>
        <p>No registered display or ordinary DICOM workspace was opened.</p>
      </main>
    );
  }
  return <App />;
}
