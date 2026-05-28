import { useQuery } from '@tanstack/react-query';
import type { Bootstrap, IndicatorLibrary } from '../types';
import { getBootstrap, getIndicatorLibrary } from '../api/strategy';

function hasLibraryData(library: IndicatorLibrary | undefined): library is IndicatorLibrary {
  return Boolean(library?.indicators?.length && library?.categories?.length);
}

export function useBootstrap() {
  return useQuery({
    queryKey: ['bootstrap'],
    queryFn: async (): Promise<Bootstrap> => {
      const bootstrap = await getBootstrap();
      const embeddedLibrary = (bootstrap as Bootstrap & { indicator_library?: IndicatorLibrary }).indicator_library;
      if (hasLibraryData(embeddedLibrary)) return bootstrap;
      try {
        const library = await getIndicatorLibrary();
        return { ...bootstrap, indicator_library: library } as Bootstrap & { indicator_library: IndicatorLibrary };
      } catch {
        return bootstrap;
      }
    },
  });
}
