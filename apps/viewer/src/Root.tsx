import { useEffect, useState } from 'react';
import App from './App';
import { RegistrationQaWorkspace } from './components/RegistrationQaWorkspace';
import { ReviewedRegistrationWorkspace } from './components/ReviewedRegistrationWorkspace';
import {
  loadRegistrationQaContext,
  type RegistrationQaContext,
} from './registrationQaService';
import {
  loadReviewedRegistrationContext,
  type ReviewedRegistrationContext,
} from './reviewedRegistrationService';

type RootState =
  | { status: 'probing' }
  | {
      status: 'reviewed-registration';
      context: ReviewedRegistrationContext;
      ordinaryOpened: boolean;
    }
  | { status: 'registration-qa'; context: RegistrationQaContext }
  | {
      status: 'dicom-viewer';
      reviewedContext?: ReviewedRegistrationContext;
      reviewedWarning?: string;
    }
  | { status: 'qa-error'; message: string };

export default function Root() {
  const [state, setState] = useState<RootState>({ status: 'probing' });

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      const reviewedResult = await loadReviewedRegistrationContext(controller.signal);
      if (controller.signal.aborted) return;
      if (reviewedResult.status === 'available') {
        setState({
          status: 'reviewed-registration',
          context: reviewedResult.context,
          ordinaryOpened: false,
        });
        return;
      }
      if (reviewedResult.status === 'error') {
        setState({
          status: 'dicom-viewer',
          reviewedWarning: reviewedResult.message,
        });
        return;
      }

      const qaResult = await loadRegistrationQaContext(controller.signal);
      if (controller.signal.aborted) return;
      if (qaResult.status === 'available') {
        setState({ status: 'registration-qa', context: qaResult.context });
      } else if (qaResult.status === 'none') {
        setState({ status: 'dicom-viewer' });
      } else {
        setState({ status: 'qa-error', message: qaResult.message });
      }
    })();
    return () => controller.abort();
  }, []);

  if (state.status === 'probing') {
    return (
      <main className="qa-probe">
        <p className="eyebrow">ScanView local workspace</p>
        <h1>Checking local display authorization…</h1>
      </main>
    );
  }
  if (state.status === 'registration-qa') {
    return <RegistrationQaWorkspace context={state.context} />;
  }
  if (state.status === 'qa-error') {
    return (
      <main className="qa-probe qa-error-state" role="alert">
        <p className="eyebrow">Registration QA unavailable</p>
        <h1>Local QA session failed closed</h1>
        <p>{state.message}</p>
        <p>No registered display or ordinary DICOM workspace was opened.</p>
      </main>
    );
  }
  const showingReviewed = state.status === 'reviewed-registration';
  const reviewedContext = showingReviewed ? state.context : state.reviewedContext;
  const ordinaryMounted = !showingReviewed || state.ordinaryOpened;

  return (
    <>
      {ordinaryMounted && (
        <div
          className="ordinary-viewer-surface"
          hidden={showingReviewed}
          inert={showingReviewed ? true : undefined}
          aria-hidden={showingReviewed ? true : undefined}
        >
          <App active={!showingReviewed} />
        </div>
      )}
      {showingReviewed && (
        <ReviewedRegistrationWorkspace
          context={state.context}
          onExit={() =>
            setState({ status: 'dicom-viewer', reviewedContext: state.context })
          }
        />
      )}
      {!showingReviewed && reviewedContext && (
        <aside className="reviewed-entry-banner">
          <div>
            <strong>Accepted exploratory registration is available.</strong>
            <span>
              Self-attested · shared-coverage opacity/swipe only · not for diagnosis
            </span>
          </div>
          <button
            type="button"
            autoFocus
            onClick={() =>
              setState({
                status: 'reviewed-registration',
                context: reviewedContext,
                ordinaryOpened: true,
              })
            }
          >
            Open reviewed registration
          </button>
        </aside>
      )}
      {!showingReviewed && state.reviewedWarning && (
        <aside className="reviewed-warning-banner" role="alert">
          <strong>Registered display remains locked.</strong>
          <span>{state.reviewedWarning} Ordinary local DICOM remains available.</span>
        </aside>
      )}
    </>
  );
}
