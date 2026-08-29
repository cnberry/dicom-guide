import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DicomSeries } from './dicom';
import {
  PRESENTATION_STATE_ENDPOINT,
  PRESENTATION_STATE_LIMITATIONS,
  PRESENTATION_STATE_MAX_BYTES,
  loadPresentationStateCatalog,
  parsePresentationStateCatalog,
  presentationPixelPointToImageIndex,
} from './presentationStates';

const STUDY = 'study_0123456789abcdef0123';
const SERIES = 'series_0123456789abcdef0123';
const PR_SERIES = 'series_1123456789abcdef0123';
const PATIENT = 'patient_0123456789abcdef0123';
const INSTANCE_A = 'instance_0123456789abcdef0123';
const INSTANCE_B = 'instance_1123456789abcdef0123';
const PR_INSTANCE = 'instance_2123456789abcdef0123';

const localSeries = (): DicomSeries[] => [
  {
    id: SERIES,
    studyId: STUDY,
    patientContextId: PATIENT,
    modality: 'CT',
    description: 'Synthetic CT',
    imageType: ['ORIGINAL', 'PRIMARY'],
    sourceKind: 'loopback-service',
    geometry: { rows: 512, columns: 512 },
    instances: [INSTANCE_A, INSTANCE_B].map((instanceId, index) => ({
      instanceId,
      instanceNumber: index + 1,
    })),
  },
];

const catalog = () => ({
  schema_version: '1.0.0',
  artifact_type: 'scanview.presentation-state-catalog',
  generated_at: '2026-08-29T12:00:00Z',
  catalog_content_sha256: 'a'.repeat(64),
  local_only: true,
  privacy: {
    classification: 'sensitive_local_medical_data',
    direct_identifier_tags_excluded: true,
    annotation_text_may_contain_identifiers: true,
    deidentified: false,
    contains_pixels: false,
    contains_paths: false,
    contains_annotation_text: true,
  },
  state_count: 1,
  supported_state_count: 1,
  unsupported_state_count: 0,
  states: [
    {
      presentation_state_id: PR_INSTANCE,
      source: {
        study_id: STUDY,
        series_id: PR_SERIES,
        instance_id: PR_INSTANCE,
        patient_context_id: PATIENT,
        bytes: 4096,
        sha256: 'b'.repeat(64),
      },
      display_status: 'supported_read_only',
      referenced_series: [
        {
          study_id: STUDY,
          series_id: SERIES,
          patient_context_id: PATIENT,
          modality: 'CT',
          instance_ids: [INSTANCE_A, INSTANCE_B],
        },
      ],
      referenced_instance_count: 2,
      presentation: {
        rotation_degrees: 0,
        horizontal_flip: false,
        modality_transform: 'SOURCE_EQUIVALENT_LINEAR',
        voi_lut_function: 'LINEAR',
        presentation_lut_shape: 'IDENTITY',
        source_pixel_aspect_ratio_verified: true,
        window_center: 40,
        window_width: 400,
        voi_range: { lower: -160, upper: 239 },
        displayed_area: {
          top_left: [1, 1],
          bottom_right: [512, 512],
          presentation_size_mode: 'SCALE TO FIT',
        },
        annotation_style: 'scanview_high_contrast_source_geometry',
      },
      annotations: [
        {
          annotation_id: 'annotation_001',
          graphic_layer: 'LAYER 0',
          referenced_instance_ids: [INSTANCE_B],
          graphics: [
            {
              graphic_id: 'graphic_01',
              type: 'POLYLINE',
              units: 'PIXEL',
              filled: false,
              points: [[10.5, 20.5], [30.5, 40.5]],
            },
          ],
          texts: [
            {
              text_id: 'text_01',
              units: 'PIXEL',
              anchor_point: [31, 41],
              anchor_point_visible: true,
              unformatted_text: '12.3 mm',
            },
          ],
        },
      ],
      annotation_count: 1,
      graphic_count: 1,
      text_count: 1,
      author_identity_authenticated: false,
      scanview_interpretation_added: false,
      source_text_clinical_meaning: 'not_assessed',
    },
  ],
  unsupported_states: [],
  permissions: {
    exact_source_navigation_authorized: true,
    apply_saved_voi_authorized: true,
    display_source_annotations_authorized: true,
    edit_source_annotations_authorized: false,
    interpret_annotation_text_as_measurement_authorized: false,
    author_identity_authenticated: false,
    diagnosis_authorized: false,
    response_classification_authorized: false,
    clinical_conclusion_authorized: false,
  },
  limitations: [...PRESENTATION_STATE_LIMITATIONS],
});

afterEach(() => vi.unstubAllGlobals());

describe('source-bound GSPS presentation states', () => {
  it('strictly resolves an annotated source target without interpreting source text', () => {
    const resolved = parsePresentationStateCatalog(catalog(), localSeries());

    expect(resolved.states).toHaveLength(1);
    expect(resolved.states[0].targets).toEqual([
      {
        seriesId: SERIES,
        instanceId: INSTANCE_B,
        instanceIndex: 1,
        stackPosition: 2,
        stackCount: 2,
        modality: 'CT',
        seriesDescription: 'Synthetic CT',
        basis: 'source_annotation',
      },
    ]);
    expect(resolved.states[0].state.presentation.voi_range).toEqual({
      lower: -160,
      upper: 239,
    });
    expect(resolved.catalog.permissions.interpret_annotation_text_as_measurement_authorized).toBe(
      false,
    );
  });

  it('maps DICOM PIXEL corner coordinates to image-index centers explicitly', () => {
    expect(presentationPixelPointToImageIndex([0, 0])).toEqual([-0.5, -0.5, 0]);
    expect(presentationPixelPointToImageIndex([512, 512])).toEqual([511.5, 511.5, 0]);
    expect(presentationPixelPointToImageIndex([10.5, 20.5])).toEqual([10, 20, 0]);
  });

  it('fails closed on extra fields, arithmetic drift, missing sources, and authority escalation', () => {
    const extra = catalog() as ReturnType<typeof catalog> & { finding?: string };
    extra.finding = 'unsafe';
    expect(() => parsePresentationStateCatalog(extra, localSeries())).toThrow('contract');

    const drift = catalog();
    drift.states[0].presentation.voi_range.upper = 240;
    expect(() => parsePresentationStateCatalog(drift, localSeries())).toThrow(
      'does not match',
    );

    const unavailable = catalog();
    unavailable.states[0].referenced_series[0].instance_ids[1] =
      'instance_aaaaaaaaaaaaaaaaaaaa';
    expect(() => parsePresentationStateCatalog(unavailable, localSeries())).toThrow(
      'does not match',
    );

    const authority = catalog();
    authority.permissions.diagnosis_authorized = true;
    expect(() => parsePresentationStateCatalog(authority, localSeries())).toThrow('contract');

    const crossStudy = catalog();
    crossStudy.states[0].source.study_id = 'study_1123456789abcdef0123';
    expect(() => parsePresentationStateCatalog(crossStudy, localSeries())).toThrow(
      'does not match',
    );

    const extendedDisplayedArea = catalog();
    extendedDisplayedArea.states[0].presentation.displayed_area.bottom_right = [513, 513];
    expect(() => parsePresentationStateCatalog(extendedDisplayedArea, localSeries())).toThrow(
      'does not match',
    );
  });

  it('rejects unsafe geometry and text before either can be rendered', () => {
    const geometry = catalog();
    geometry.states[0].annotations[0].graphics[0].points[0] = [700, 20];
    expect(() => parsePresentationStateCatalog(geometry, localSeries())).toThrow(
      'does not match',
    );

    const text = catalog();
    text.states[0].annotations[0].texts[0].unformatted_text = 'bad\ttext';
    expect(() => parsePresentationStateCatalog(text, localSeries())).toThrow(
      'does not match',
    );
  });

  it('loads only from the same-origin local endpoint and reports source lock conflicts', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(catalog()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const loaded = await loadPresentationStateCatalog(localSeries());
    expect(loaded.states).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith(PRESENTATION_STATE_ENDPOINT, {
      cache: 'no-store',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal: undefined,
    });

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('{}', { status: 409 })),
    );
    await expect(loadPresentationStateCatalog(localSeries())).rejects.toThrow(
      'source bytes changed',
    );
  });

  it('enforces a bounded browser response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('{}', {
          status: 200,
          headers: { 'Content-Length': String(PRESENTATION_STATE_MAX_BYTES + 1) },
        }),
      ),
    );
    await expect(loadPresentationStateCatalog(localSeries())).rejects.toThrow('32 MiB');
  });
});
