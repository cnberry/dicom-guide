import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DicomSeries } from './dicom';
import {
  SOURCE_SEGMENTATION_LIMITATIONS,
  loadSourceSegmentationMask,
  readSourceSegmentationCatalog,
  type SourceSegmentationCatalog,
} from './sourceSegmentations';

const ids = {
  study: `study_${'1'.repeat(20)}`,
  sourceSeries: `series_${'2'.repeat(20)}`,
  segSeries: `series_${'3'.repeat(20)}`,
  patient: `patient_${'4'.repeat(20)}`,
  seg: `instance_${'5'.repeat(20)}`,
  instances: [1, 2, 3].map((index) =>
    `instance_${String(index + 5).repeat(20)}`),
};

const sourceSeries = (): DicomSeries => ({
  id: ids.sourceSeries,
  studyId: ids.study,
  patientContextId: ids.patient,
  acquisitionDate: '20260101',
  modality: 'MR',
  description: 'Synthetic source',
  imageType: ['ORIGINAL', 'PRIMARY'],
  frameOfReferenceId: `frame_${'9'.repeat(20)}`,
  sourceKind: 'loopback-service',
  geometry: {
    rows: 2,
    columns: 2,
    pixelSpacing: [1, 1],
    sliceThickness: 2,
    orientation: [1, 0, 0, 0, 1, 0],
  },
  instances: ids.instances.map((instanceId, index) => ({
    instanceId,
    imageUrl: `/v1/instances/${instanceId}`,
    instanceNumber: index + 1,
    imagePosition: [0, 0, index * 2],
    rows: 2,
    columns: 2,
    pixelSpacing: [1, 1],
    sliceThickness: 2,
    orientation: [1, 0, 0, 0, 1, 0],
    numberOfFrames: 1,
  })),
});

const digest = async (bytes: Uint8Array): Promise<string> => {
  const owned = new Uint8Array(bytes.byteLength);
  owned.set(bytes);
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', owned.buffer)))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
};

const artifact = async (): Promise<SourceSegmentationCatalog> => {
  const mask = new Uint8Array([1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0]);
  return {
    schema_version: '2.0.0',
    artifact_type: 'scanview.source-segmentation-catalog',
    generated_at: '2026-08-29T12:00:00Z',
    catalog_content_sha256: 'a'.repeat(64),
    local_only: true,
    privacy: {
      classification: 'sensitive_local_medical_data',
      direct_identifier_tags_excluded: true,
      segment_text_may_contain_identifiers: true,
      deidentified: false,
      contains_pixels: false,
      contains_paths: false,
      contains_segment_text: true,
    },
    segmentation_count: 1,
    supported_segmentation_count: 1,
    unsupported_segmentation_count: 0,
    segment_count: 1,
    segmentations: [{
      segmentation_id: ids.seg,
      source: {
        study_id: ids.study,
        series_id: ids.segSeries,
        instance_id: ids.seg,
        patient_context_id: ids.patient,
        bytes: 1024,
        sha256: 'b'.repeat(64),
      },
      display_status: 'supported_read_only',
      referenced_series: {
        study_id: ids.study,
        series_id: ids.sourceSeries,
        patient_context_id: ids.patient,
        modality: 'MR',
        ordered_instance_ids: [...ids.instances],
        referenced_instance_ids: [ids.instances[0], ids.instances[1]],
      },
      referenced_instance_count: 2,
      spatial_location_evidence: 'explicit_yes_and_exact_native_geometry',
      grid: {
        relationship: 'exact_native_source_grid',
        dimensions: [3, 2, 2],
        pixel_spacing_mm: [1, 1],
        projected_slice_spacing_mm: 2,
        voxel_volume_mm3: 2,
        resampled_by_scanview: false,
      },
      frame_count: 2,
      segment_count: 1,
      segments: [{
        segment_number: 1,
        segment_label: 'Source segment label',
        algorithm_type: 'MANUAL',
        algorithm_name: null,
        property_category: {
          value: '49755003',
          scheme: 'SCT',
          meaning: 'Morphologically Abnormal Structure',
        },
        property_type: {
          value: '52988006',
          scheme: 'SCT',
          meaning: 'Lesion',
        },
        recommended_display_cielab: [40000, 30000, 50000],
        frame_count: 2,
        marked_voxel_count: 2,
        computed_volume_mm3: 4,
        computed_volume_ml: 0.004,
        mask_sha256: await digest(mask),
      }],
      creator_identity_authenticated: false,
      source_segment_clinical_meaning: 'not_assessed',
      scanview_interpretation_added: false,
    }],
    unsupported_segmentations: [],
    permissions: {
      bearer_agent_sensitive_catalog_read_authorized: true,
      bearer_agent_mask_read_authorized: false,
      browser_session_sensitive_catalog_read_authorized: true,
      browser_session_mask_read_authorized: true,
      browser_session_exact_source_navigation_authorized: true,
      browser_session_read_only_mask_display_authorized: true,
      browser_session_technical_volume_display_authorized: true,
      edit_source_segmentation_authorized: false,
      convert_to_scanview_measurement_authorized: false,
      creator_identity_authenticated: false,
      segment_accuracy_verified: false,
      diagnosis_authorized: false,
      response_classification_authorized: false,
      clinical_conclusion_authorized: false,
    },
    limitations: [...SOURCE_SEGMENTATION_LIMITATIONS],
  };
};

afterEach(() => vi.restoreAllMocks());

describe('strict source-carried DICOM SEG catalog', () => {
  it('rejoins an exact native source grid and rejects altered technical arithmetic', async () => {
    const input = await artifact();
    const resolved = readSourceSegmentationCatalog(input, [sourceSeries()]);
    expect(resolved?.segmentations).toHaveLength(1);
    expect(resolved?.segmentations[0].state.segments[0].computed_volume_ml).toBe(0.004);

    const completeSeriesReference = await artifact();
    completeSeriesReference.segmentations[0].referenced_series.referenced_instance_ids = [
      ...ids.instances,
    ];
    completeSeriesReference.segmentations[0].referenced_instance_count = 3;
    expect(
      readSourceSegmentationCatalog(completeSeriesReference, [sourceSeries()]),
    ).toBeDefined();

    const optionalSpatialTag = await artifact();
    optionalSpatialTag.segmentations[0].spatial_location_evidence =
      'optional_tag_absent_exact_native_geometry';
    expect(
      readSourceSegmentationCatalog(optionalSpatialTag, [sourceSeries()]),
    ).toBeDefined();

    const invalidSpatialEvidence = await artifact();
    Object.assign(invalidSpatialEvidence.segmentations[0], {
      spatial_location_evidence: 'unverified',
    });
    expect(
      readSourceSegmentationCatalog(invalidSpatialEvidence, [sourceSeries()]),
    ).toBeUndefined();

    const altered = structuredClone(input);
    altered.segmentations[0].segments[0].computed_volume_ml = 4;
    expect(readSourceSegmentationCatalog(altered, [sourceSeries()])).toBeUndefined();
  });

  it('requires independently derived physical mask order, including a negative normal', async () => {
    const reversedTamper = await artifact();
    reversedTamper.segmentations[0].referenced_series.ordered_instance_ids.reverse();
    expect(readSourceSegmentationCatalog(reversedTamper, [sourceSeries()])).toBeUndefined();

    const negativeNormalSeries = sourceSeries();
    negativeNormalSeries.geometry.orientation = [1, 0, 0, 0, -1, 0];
    negativeNormalSeries.instances.forEach((instance) => {
      instance.orientation = [1, 0, 0, 0, -1, 0];
    });
    const negativeNormalArtifact = await artifact();
    negativeNormalArtifact.segmentations[0].referenced_series.ordered_instance_ids.reverse();
    expect(
      readSourceSegmentationCatalog(negativeNormalArtifact, [negativeNormalSeries]),
    ).toBeDefined();

    const wrongMembership = await artifact();
    wrongMembership.segmentations[0].referenced_series.ordered_instance_ids[2] =
      `instance_${'f'.repeat(20)}`;
    expect(readSourceSegmentationCatalog(wrongMembership, [sourceSeries()])).toBeUndefined();

    const widened = await artifact();
    (widened.permissions as Record<string, boolean>).diagnosis_authorized = true;
    expect(readSourceSegmentationCatalog(widened, [sourceSeries()])).toBeUndefined();

    const wrongCount = await artifact();
    wrongCount.segment_count = 2;
    expect(readSourceSegmentationCatalog(wrongCount, [sourceSeries()])).toBeUndefined();

    const hiddenText = await artifact();
    hiddenText.privacy.contains_segment_text = false;
    expect(readSourceSegmentationCatalog(hiddenText, [sourceSeries()])).toBeUndefined();

    const impossibleFrames = await artifact();
    impossibleFrames.segmentations[0].segments[0].frame_count = 4;
    impossibleFrames.segmentations[0].frame_count = 4;
    expect(readSourceSegmentationCatalog(impossibleFrames, [sourceSeries()])).toBeUndefined();
  });

  it('rehashes a browser-session-only dense binary mask before returning it', async () => {
    const input = await artifact();
    const resolved = readSourceSegmentationCatalog(input, [sourceSeries()])!;
    const bytes = new Uint8Array([1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0]);
    vi.stubGlobal('fetch', vi.fn(async () => new Response(bytes, {
      status: 200,
      headers: {
        'Content-Type': 'application/vnd.scanview.source-binary-mask',
        'Content-Length': String(bytes.byteLength),
        'X-Content-SHA256': input.segmentations[0].segments[0].mask_sha256,
      },
    })));

    const loaded = await loadSourceSegmentationMask(
      resolved.segmentations[0],
      resolved.segmentations[0].state.segments[0],
    );
    expect(Array.from(loaded.mask)).toEqual(Array.from(bytes));
    expect(loaded.segment.marked_voxel_count).toBe(2);
    expect(fetch).toHaveBeenCalledWith(
      `/v1/source-segmentations/${ids.seg}/masks/1`,
      expect.objectContaining({ credentials: 'same-origin' }),
    );

    const changed = new Uint8Array(bytes);
    changed[0] = 0;
    vi.stubGlobal('fetch', vi.fn(async () => new Response(changed, {
      status: 200,
      headers: {
        'Content-Type': 'application/vnd.scanview.source-binary-mask',
        'Content-Length': String(changed.byteLength),
        'X-Content-SHA256': input.segmentations[0].segments[0].mask_sha256,
      },
    })));
    await expect(loadSourceSegmentationMask(
      resolved.segmentations[0],
      resolved.segmentations[0].state.segments[0],
    )).rejects.toThrow(/exact local validation/i);
  });
});
