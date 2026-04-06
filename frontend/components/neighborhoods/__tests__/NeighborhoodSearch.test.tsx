import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { NeighborhoodSearch } from '../NeighborhoodSearch';

describe('NeighborhoodSearch', () => {
  it('uses the default placeholder and relays query changes', async () => {
    const onQueryChange = jest.fn();
    const user = userEvent.setup();

    function ControlledHarness() {
      const [query, setQuery] = React.useState('');

      return (
        <NeighborhoodSearch
          query={query}
          onQueryChange={(nextQuery) => {
            onQueryChange(nextQuery);
            setQuery(nextQuery);
          }}
        />
      );
    }

    render(<ControlledHarness />);

    const input = screen.getByTestId('neighborhood-search-input');
    expect(input).toHaveAttribute('placeholder', 'Search neighborhoods...');

    await user.type(input, 'Astoria');

    expect(onQueryChange).toHaveBeenLastCalledWith('Astoria');
  });
});
