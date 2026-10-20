from newshound import main


def test_main_runs(capsys):
    main()
    assert "newshound" in capsys.readouterr().out
