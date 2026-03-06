export const persistHomeNavContext = (categoryId: string) => {
  if (typeof window !== 'undefined') {
    sessionStorage.setItem('navigationFrom', '/');
    if (categoryId) {
      sessionStorage.setItem('homeSelectedCategory', categoryId);
      return;
    }
    sessionStorage.removeItem('homeSelectedCategory');
  }
};
