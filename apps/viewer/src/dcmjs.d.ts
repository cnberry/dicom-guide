declare module 'dcmjs' {
  type NaturalizedDataset = Record<string, unknown> & {
    _meta?: Record<string, unknown>;
  };

  const dcmjs: {
    data: {
      datasetToDict: (dataset: NaturalizedDataset) => {
        write: () => ArrayBuffer;
      };
      DicomMetaDictionary: {
        uid: () => string;
      };
      Colors: {
        rgb2DICOMLAB: (rgb: number[]) => number[];
      };
    };
  };

  export default dcmjs;
}
