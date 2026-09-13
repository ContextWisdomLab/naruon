module.exports = {
  hooks: {
    readPackage(pkg) {
      if (pkg.dependencies && pkg.dependencies.postcss) {
        pkg.dependencies.postcss = '^8.5.15';
      }
      if (pkg.peerDependencies && pkg.peerDependencies.postcss) {
        pkg.peerDependencies.postcss = '^8.5.15';
      }
      if (pkg.devDependencies && pkg.devDependencies.postcss) {
        pkg.devDependencies.postcss = '^8.5.15';
      }
      return pkg;
    }
  }
};
