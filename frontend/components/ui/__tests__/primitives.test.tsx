import { render, screen } from '@testing-library/react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '../card';
import { Avatar, AvatarFallback, AvatarImage } from '../avatar';

describe('ui primitives', () => {
  it('renders card subcomponents together', () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>Fine-grained layout</CardDescription>
        </CardHeader>
        <CardContent>Body</CardContent>
        <CardFooter>Footer</CardFooter>
      </Card>,
    );

    expect(screen.getByText('Profile')).toBeInTheDocument();
    expect(screen.getByText('Fine-grained layout')).toBeInTheDocument();
    expect(screen.getByText('Body')).toBeInTheDocument();
    expect(screen.getByText('Footer')).toBeInTheDocument();
  });

  it('renders avatar root, image, and fallback content', () => {
    const { container } = render(
      <Avatar>
        <AvatarImage alt="Student" src="/avatar.png" />
        <AvatarFallback>ST</AvatarFallback>
      </Avatar>,
    );

    expect(screen.getByText('ST')).toBeInTheDocument();
    expect(container.querySelector('.rounded-full')).toBeInTheDocument();
  });
});
