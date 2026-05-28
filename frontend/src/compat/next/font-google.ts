interface FontOptions {
  variable?: string;
  subsets?: string[];
}

interface FontDefinition {
  variable: string;
  className: string;
  style: Record<string, never>;
}

function buildFont(options: FontOptions = {}): FontDefinition {
  return {
    variable: options.variable ?? '',
    className: '',
    style: {},
  };
}

export function Geist(options?: FontOptions) {
  return buildFont(options);
}

export function Geist_Mono(options?: FontOptions) {
  return buildFont(options);
}