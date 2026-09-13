module.exports = {
  hooks: {
    readPackage(pkg, context) {
      if (pkg.name === 'next') {
        if (pkg.dependencies) delete pkg.dependencies['sharp'];
        if (pkg.optionalDependencies) delete pkg.optionalDependencies['sharp'];
        if (pkg.peerDependencies) delete pkg.peerDependencies['sharp'];
      }
      return pkg;
    }
  }
};
