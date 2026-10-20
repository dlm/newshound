{
  description = "newshound - autonomous agent that scrapes, scores, and serves a personal RSS feed";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-25.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      ...
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            git
            jujutsu # nixpkgs#jj is a *different* package (a JSON stream editor) - use jujutsu
            just

            python313
            uv
            ruff
          ];
        };
      }
    );
}
